from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, create_engine
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import os, json, re, uuid, requests

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
    title="Healthcare Symptom Checker (Ollama)",
    version="2.0",
    lifespan=lifespan
)

# Allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# HELPER — QUERY OLLAMA
# -----------------------------
def query_ollama(model: str, system_prompt: str, user_prompt: str) -> str:
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "stream": False
    }
    try:
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()
        if "message" in data and "content" in data["message"]:
            return data["message"]["content"]
        elif "messages" in data and isinstance(data["messages"], list):
            return data["messages"][-1]["content"]
        else:
            raise ValueError("Unexpected Ollama response format.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama request failed: {str(e)}")

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
            metadata={"model": "ollama", "prompt_version": "v1"}
        )

    red_flags = detect_red_flags(sanitized_text)
    if red_flags:
        return ModelResponse(
            disclaimer="Educational only — not medical advice. Seek immediate medical attention.",
            escalation={"level": "emergency", "message": f"Red-flag symptoms detected: {', '.join(red_flags)}. Seek emergency care."},
            probable_conditions=[],
            next_steps=["Call emergency services or go to the nearest emergency department."],
            metadata={"model": "ollama", "prompt_version": "v1"}
        )

    # Construct user prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(
        symptoms=sanitized_text,
        age=query.age if query.age is not None else "unknown",
        pregnant=str(query.pregnant).lower() if query.pregnant is not None else "unknown",
        chronic=query.chronic_conditions or "none"
    )

    # Explicitly ask for JSON output
    json_request = (
        "Return your answer strictly as valid JSON only, following the schema from the system prompt. "
        "Do not include any extra text or explanations outside the JSON block."
    )
    full_user_prompt = user_prompt + "\n\n" + json_request

    model_name = os.getenv("OLLAMA_MODEL", "gpt-oss:120b-cloud")
    text = query_ollama(model_name, SYSTEM_PROMPT, full_user_prompt)

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
            "metadata": {"model": "ollama", "prompt_version": "v1"}
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
                "metadata": {"model": "ollama", "prompt_version": "v1"}
            }

    # Add metadata + save to DB
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
# NEW ENDPOINT — HISTORY
# -----------------------------
@app.get("/history")
def get_history(limit: int = 10):
    from sqlmodel import select

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

# -----------------------------
# ROOT ENDPOINT
# -----------------------------
@app.get("/")
async def root():
    return {"message": "Healthcare Symptom Checker (Ollama) is running ✅"}

from sqlmodel import delete

@app.delete("/history/clear")
def clear_history():
    with Session(engine) as session:
        session.exec(delete(QueryHistory))
        session.commit()
    return {"message": "✅ History cleared"}
