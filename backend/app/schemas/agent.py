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
    score: int


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
