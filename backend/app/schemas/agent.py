from pydantic import BaseModel, Field, field_validator


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1)
    goalId: str | None = None
    materialId: str | None = None
    limit: int = Field(default=3, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        question = value.strip()
        if not question:
            raise ValueError("Question cannot be blank")
        return question


class AgentReference(BaseModel):
    materialId: str
    materialTitle: str
    chunkIndex: int
    content: str
    score: float
    searchMode: str = "keyword"


class AgentAskResponse(BaseModel):
    id: str | None = None
    materialId: str | None = None
    goalId: str | None = None
    question: str
    answer: str
    basis: str
    suggestion: str
    sourceTitle: str
    references: list[AgentReference]
    isFromMaterial: bool
    confidence: str
    createdAt: str | None = None
    mode: str = "mock"
    nextAction: str = "answer_only"
    requiresConfirmation: bool = False
    insufficiencyReason: str = ""
    reviewDrafts: list[dict] = Field(default_factory=list)


class AgentActionLogCreate(BaseModel):
    goalId: str | None = None
    actionType: str = Field(min_length=1)
    observation: str = ""
    decision: dict = Field(default_factory=dict)
    proposedPayload: dict = Field(default_factory=dict)
    status: str = Field(default="proposed", pattern="^(proposed|accepted|rejected|later|applied)$")


class AgentActionLogUpdate(BaseModel):
    status: str = Field(pattern="^(proposed|accepted|rejected|later|applied)$")


class AgentRunCreate(BaseModel):
    goalId: str | None = None
    trigger: str = Field(default="manual", pattern="^(manual|after_write|scheduled)$")
    objective: str = Field(default="", max_length=500)
    decisionMode: str = Field(default="hybrid", pattern="^(rule-based|llm-json|hybrid)$")
    maxSteps: int = Field(default=4, ge=1, le=8)

    @field_validator("objective")
    @classmethod
    def normalize_objective(cls, value: str) -> str:
        return value.strip()


class AgentRunExecute(BaseModel):
    maxSteps: int | None = Field(default=None, ge=1, le=8)


class AgentRunUpdate(BaseModel):
    status: str = Field(
        pattern="^(created|decided|running|waiting_confirmation|feedback_recorded|executed|completed|failed|max_steps|cancelled|closed)$"
    )
