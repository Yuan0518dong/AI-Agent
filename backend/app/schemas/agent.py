from pydantic import BaseModel, Field, field_validator


class AgentAskRequest(BaseModel):
    question: str = Field(min_length=1)
    goalId: str | None = None
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
    answer: str
    basis: str
    suggestion: str
    references: list[AgentReference]
    isFromMaterial: bool
    confidence: str
    mode: str = "mock"
