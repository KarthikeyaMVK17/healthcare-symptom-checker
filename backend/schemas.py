from sqlmodel import SQLModel, Field, Column, JSON
from pydantic import BaseModel
from typing import List, Optional, Literal, Dict
from datetime import datetime, timezone
import uuid

# -----------------------------
# DATABASE TABLE
# -----------------------------
class QueryHistory(SQLModel, table=True):
    """Store past user queries + responses."""
    id: Optional[int] = Field(default=None, primary_key=True)
    query_id: str = Field(default_factory=lambda: str(uuid.uuid4()), index=True)
    user_id: Optional[str] = Field(default=None, index=True)
    symptoms: str
    age: Optional[int] = None
    pregnant: Optional[bool] = None
    chronic_conditions: Optional[str] = None
    model_response: Optional[Dict] = Field(default=None, sa_column=Column(JSON))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# -----------------------------
# API SCHEMAS
# -----------------------------
class UserQuery(BaseModel):
    user_id: Optional[str] = None
    symptoms: str
    age: Optional[int] = None
    pregnant: Optional[bool] = None
    chronic_conditions: Optional[str] = None
    timestamp: datetime = datetime.now(timezone.utc)

class Escalation(BaseModel):
    level: Literal['emergency', 'urgent', 'non-urgent']
    message: str

class Condition(BaseModel):
    name: str
    confidence: Literal['LOW', 'MEDIUM', 'HIGH']
    rationale: str
    severity_score: Optional[float] = None
    risk_category: Optional[Literal['low', 'moderate', 'high']] = None
    educational_links: Optional[List[str]] = None

class ModelResponse(BaseModel):
    disclaimer: str
    escalation: Optional[Escalation] = None
    probable_conditions: List[Condition]
    next_steps: List[str]
    metadata: Dict[str, str]
    query_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    error_message: Optional[str] = None
