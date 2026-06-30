from pydantic import BaseModel, Field


class PlanGenerateRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=30)
    regenerate: bool = True


class TaskCheckInRequest(BaseModel):
    done: bool

