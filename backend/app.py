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
    version="4.0",
    lifespan=lifespan
)

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
# FRONTEND SERVING
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# This automatically serves index.html + JS + CSS from root
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

# -----------------------------
# HELPER — QUERY GEMINI
# -----------------------------
def query_gemini(model: str, prompt: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY environment variable.")

    genai.configure(api_key=api_key)
    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(prompt)
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

    if check_for_self_harm(sanitized_text):
        return ModelResponse(
            disclaimer="Educational only — not medical advice.",
            escalation={"level": "emergency", "message": "If you are in danger, call emergency services."},
            probable_conditions=[],
            next_steps=["Seek immediate help from emergency services or a crisis line."],
            metadata={"model": "gemini", "prompt_version": "v1"}
        )

    red_flags = detect_red_flags(sanitized_text)
    if red_flags:
        return ModelResponse(
            disclaimer="Educational only — not medical advice.",
            escalation={"level": "emergency", "message": f"Red-flag symptoms detected: {', '.join(red_flags)}."},
            probable_conditions=[],
            next_steps=["Go to the nearest emergency department."],
            metadata={"model": "gemini", "prompt_version": "v1"}
        )

    user_prompt = USER_PROMPT_TEMPLATE.format(
        symptoms=sanitized_text,
        age=query.age or "unknown",
        pregnant=str(query.pregnant).lower() if query.pregnant is not None else "unknown",
        chronic=query.chronic_conditions or "none"
    )
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\nReturn strictly JSON output."

    model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    text = query_gemini(model_name, full_prompt)

    try:
        match = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(match.group(0)) if match else {"error": "Unstructured response"}
    except Exception:
        data = {"error": "Failed to parse response"}

    data["metadata"] = {
        "model": "gemini",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query_id": str(uuid.uuid4())
    }

    return data

# -----------------------------
# ROOT TEST ENDPOINT
# -----------------------------
@app.get("/ping")
def ping():
    return {"status": "Server running ✅"}
