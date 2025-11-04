from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Session, create_engine, select, delete
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
import os, json, re, uuid
import google.generativeai as genai

from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .guardrails import sanitize_input, detect_red_flags, check_for_self_harm
from .schemas import UserQuery, ModelResponse, QueryHistory

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./symptom_checker.db")
engine = create_engine(DATABASE_URL, echo=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(
    title="Healthcare Symptom Checker (Gemini)",
    version="4.1",
    lifespan=lifespan
)

# -----------------------------
# Middleware
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Gemini helper
# -----------------------------
def query_gemini(model: str, prompt: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(prompt)
        return response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini request failed: {str(e)}")

# -----------------------------
# ✅ API ROUTES — must come before static mount
# -----------------------------
@app.post("/analyze", response_model=ModelResponse)
async def analyze(query: UserQuery, request: Request):
    sanitized_text, removed = sanitize_input(query.symptoms)
    if removed:
        sanitized_text += "\n(PII removed)"
    if check_for_self_harm(sanitized_text):
        return ModelResponse(
            disclaimer="Educational use only.",
            escalation={"level": "emergency", "message": "Seek immediate help."},
            probable_conditions=[],
            next_steps=["Contact emergency services immediately."],
            metadata={"model": "gemini"}
        )
    red_flags = detect_red_flags(sanitized_text)
    if red_flags:
        return ModelResponse(
            disclaimer="Educational only.",
            escalation={"level": "emergency", "message": f"Red flags: {', '.join(red_flags)}"},
            probable_conditions=[], next_steps=["Go to ER."],
            metadata={"model": "gemini"}
        )

    prompt = USER_PROMPT_TEMPLATE.format(
        symptoms=sanitized_text, age=query.age, pregnant=query.pregnant,
        chronic=query.chronic_conditions or "none"
    )
    full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}\n\nReturn JSON only."

    model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    response_text = query_gemini(model_name, full_prompt)

    try:
        match = re.search(r"\{[\s\S]*\}", response_text)
        data = json.loads(match.group(0)) if match else {"error": response_text}
    except:
        data = {"error": response_text}

    data["metadata"] = {
        "model": "gemini",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query_id": str(uuid.uuid4())
    }
    return data

@app.get("/history")
def get_history(limit: int = 10):
    with Session(engine) as session:
        statement = select(QueryHistory).order_by(QueryHistory.timestamp.desc()).limit(limit)
        records = session.exec(statement).all()
    return {"history": [{"query_id": r.query_id, "symptoms": r.symptoms, "timestamp": r.timestamp.isoformat(), "model_response": r.model_response} for r in records]}

@app.delete("/history/clear")
def clear_history():
    with Session(engine) as session:
        session.exec(delete(QueryHistory))
        session.commit()
    return {"message": "✅ History cleared"}

@app.get("/ping")
def ping():
    return {"status": "API running fine ✅"}

# -----------------------------
# 🚀 Static frontend mount (AFTER routes)
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
