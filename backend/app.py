from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Session, create_engine, select, delete
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
import os, json, re, uuid, logging
import google.generativeai as genai

# --- Import project modules ---
from .prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .guardrails import sanitize_input, detect_red_flags, check_for_self_harm
from .schemas import UserQuery, ModelResponse, QueryHistory

# ============================================================
# ✅ CONFIGURATION
# ============================================================

# Logging setup — ensures all errors print to Render logs
logging.basicConfig(level=logging.INFO)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./symptom_checker.db")
engine = create_engine(DATABASE_URL, echo=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB at startup."""
    SQLModel.metadata.create_all(engine)
    yield

app = FastAPI(
    title="Healthcare Symptom Checker (Gemini)",
    version="5.0",
    lifespan=lifespan
)

# ============================================================
# ✅ MIDDLEWARE
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# ✅ GEMINI HELPER
# ============================================================

def query_gemini(model: str, prompt: str) -> str:
    """Send query to Gemini API and return text output."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing GOOGLE_API_KEY environment variable.")

    genai.configure(api_key=api_key)

    try:
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(prompt)
        logging.info(f"✅ Gemini response received: {response}")
        return response.text or "No response text returned."
    except Exception as e:
        logging.exception("❌ Gemini request failed.")
        raise HTTPException(status_code=500, detail=f"Gemini request failed: {str(e)}")

# ============================================================
# ✅ API ROUTES (declare before frontend mount!)
# ============================================================

@app.post("/analyze", response_model=ModelResponse)
async def analyze(query: UserQuery, request: Request):
    """Analyze user symptoms using Gemini."""
    logging.info(f"🧠 Received symptoms: {query.symptoms}")

    sanitized_text, removed = sanitize_input(query.symptoms)
    if removed:
        sanitized_text += "\n(PII removed)"

    # --- Safety checks ---
    if check_for_self_harm(sanitized_text):
        return ModelResponse(
            disclaimer="Educational only — not medical advice.",
            escalation={"level": "emergency", "message": "If in danger, contact emergency services."},
            probable_conditions=[],
            next_steps=["Contact local emergency services or helpline."],
            metadata={"model": "gemini"}
        )

    red_flags = detect_red_flags(sanitized_text)
    if red_flags:
        return ModelResponse(
            disclaimer="Educational only — not medical advice.",
            escalation={"level": "emergency", "message": f"Red-flag symptoms: {', '.join(red_flags)}"},
            probable_conditions=[],
            next_steps=["Visit an emergency department immediately."],
            metadata={"model": "gemini"}
        )

    # --- Prepare prompt ---
    user_prompt = USER_PROMPT_TEMPLATE.format(
        symptoms=sanitized_text,
        age=query.age or "unknown",
        pregnant=str(query.pregnant).lower() if query.pregnant is not None else "unknown",
        chronic=query.chronic_conditions or "none"
    )

    model_name = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    full_prompt = f"{SYSTEM_PROMPT}\n\n{user_prompt}\n\nReturn only valid JSON following the described schema."

    # --- Query Gemini ---
    try:
        text = query_gemini(model_name, full_prompt)
    except HTTPException as e:
        logging.error(f"Gemini call failed: {e.detail}")
        raise

    # --- Parse JSON safely ---
    try:
        match = re.search(r"\{[\s\S]*\}", text)
        data = json.loads(match.group(0)) if match else None
    except Exception as e:
        logging.warning(f"⚠️ JSON parsing failed: {e}")
        data = None

    if not data:
        data = {
            "disclaimer": "Educational only — not medical advice.",
            "escalation": None,
            "probable_conditions": [{"name": "Unclear", "confidence": "LOW", "rationale": text[:300]}],
            "next_steps": ["Try again or consult a doctor."],
            "metadata": {"model": "gemini"}
        }

    # --- Add metadata ---
    data["metadata"]["timestamp"] = datetime.now(timezone.utc).isoformat()
    data["metadata"]["query_id"] = str(uuid.uuid4())

    # --- Save history to DB ---
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

@app.get("/history")
def get_history(limit: int = 10):
    """Return recent user queries."""
    with Session(engine) as session:
        records = session.exec(
            select(QueryHistory).order_by(QueryHistory.timestamp.desc()).limit(limit)
        ).all()
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
    """Clear all query history."""
    with Session(engine) as session:
        session.exec(delete(QueryHistory))
        session.commit()
    return {"message": "✅ History cleared"}

@app.get("/ping")
def ping():
    return {"status": "Server running fine ✅"}

# ============================================================
# ✅ FRONTEND STATIC FILE SERVING
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

# Mount frontend (AFTER defining API routes!)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

logging.info("✅ FastAPI app initialized successfully.")
