from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Session, create_engine, select, delete
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import os, json, re, uuid
import google.generativeai as genai

from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .guardrails import sanitize_input, detect_red_flags, check_for_self_harm
from .schemas import UserQuery, ModelResponse, QueryHistory

# -----------------------------
# DATABASE SETUP
# -----------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./symptom_checker.db")
engine = create_engine(DATABASE_URL, echo=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB when app starts."""
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(
    title="Healthcare Symptom Checker (Gemini)",
    version="3.2",
    lifespan=lifespan
)

# -----------------------------
# FRONTEND SERVING
# -----------------------------
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
frontend_dir = os.path.abspath(frontend_dir)

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def serve_frontend():
    index_path = os.path.join(frontend_dir, "index.html")
    return FileResponse(index_path)

# -----------------------------
# CORS MIDDLEWARE
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# HELPER — QUERY GEMINI
# -----------------------------
def query_gemini(model: str, system_prompt: str, user_prompt: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY environment variable.")
    
    genai.configure(api_key=api_key)
    try:
        full_prompt = f"{system_prompt}\n\nUser:\n{user_prompt}"
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(full_prompt)
        return response.text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini request failed: {str(e)}")

# -----------------------------
# MAIN ENDPOINT — ANALYZE SYMPTOMS
# -----------------------------
@app.post("/analyze", response_model=ModelResponse)
async def analyze(query: UserQuery, request: Request):
    sanitized_text, removed = sanitize_input(query.symptoms)
    if removed:
        sanitized_text += "\n(PII removed)"

    # Handle self-harm and red-flag detection
    if check_for_self_harm(sanitized_text):
        return ModelResponse(
            disclaimer="Educational only — not medical advice. If you are in danger, call emergency services.",
            escalation={"level": "emergency", "message": "If you or someone is at immediate risk, call emergency services or a suicide hotline."},
            probable_conditions=[],
            next_steps=["Seek immediate help from emergency services or a local crisis line."],
            metadata={"model": "gemini", "prompt_version": "v1"}
        )

    red_flags = detect_red_flags(sanitized_text)
    if red_flags:
        return ModelResponse(
            disclaimer="Educational only — not medical advice. Seek immediate medical attention.",
            escalation={"level": "emergency", "message": f"Red-flag symptoms detected: {', '.join(red_flags)}. Seek emergency care."},
            probable_conditions=[],
            next_steps=["Call emergency services or go to the nearest emergency department."],
            metadata={"model": "gemini", "prompt_version": "v1"}
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        symptoms=sanitized_text,
        age=query.age if query.age is not None else "unknown",
        pregnant=str(query.pregnant).lower() if query.pregnant is not None else "unknown",
        chronic=query.chronic_conditions or "none"
    )

    json_request = (
        "Return your answer strictly as valid JSON only, following the schema from the system prompt. "
        "Do not include any extra text or explanations outside the JSON block."
    )
    full_user_prompt = user_prompt + "\n\n" + json_request

    model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    text = query_gemini(model_name, SYSTEM_PROMPT, full_user_prompt)

    # Try extracting JSON
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        data = {
            "disclaimer": "Educational only — not medical advice.",
            "escalation": None,
            "probable_conditions": [{
                "name": "Unclear response",
                "confidence": "LOW",
                "rationale": text[:300]
            }],
            "next_steps": [
                "Try rephrasing your symptoms.",
                "If this persists, consult a healthcare professional."
            ],
            "metadata": {"model": "gemini", "prompt_version": "v1"}
        }
    else:
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            data = {
                "disclaimer": "Educational only — not medical advice.",
                "escalation": None,
                "probable_conditions": [{
                    "name": "Invalid JSON",
                    "confidence": "LOW",
                    "rationale": text[:300]
                }],
                "next_steps": [
                    "Model output could not be parsed correctly.",
                    "Try again or check backend logs."
                ],
                "metadata": {"model": "gemini", "prompt_version": "v1"}
            }

    data["metadata"]["timestamp"] = datetime.now(timezone.utc).isoformat()
    data["metadata"]["query_id"] = str(uuid.uuid4())

    with Session(engine) as session:
        record = QueryHistory(
            query_id=data["metadata"]["query_id"],
            user_id=query.user_id,
            symptoms=query.symptoms,
            age=query.age,
            pregnant=query.pregnant,
            chronic_conditions=query.chronic_conditions,
            model_response=data
        )
        session.add(record)
        session.commit()

    return ModelResponse(**data)

# -----------------------------
# HISTORY ENDPOINTS
# -----------------------------
@app.get("/history")
def get_history(limit: int = 10):
    with Session(engine) as session:
        statement = (
            select(QueryHistory)
            .order_by(QueryHistory.timestamp.desc())
            .limit(limit)
        )
        result = session.exec(statement)
        records = result.all()

    return {
        "history": [
            {
                "query_id": r.query_id,
                "symptoms": r.symptoms,
                "timestamp": r.timestamp.isoformat(),
                "model_response": r.model_response,
            }
            for r in records
        ]
    }

@app.delete("/history/clear")
def clear_history():
    with Session(engine) as session:
        session.exec(delete(QueryHistory))
        session.commit()
    return {"message": "✅ History cleared"}
