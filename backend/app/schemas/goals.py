from datetime import date

from pydantic import BaseModel, Field


class GoalCreate(BaseModel):
    name: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    level: str = Field(min_length=1)
    deadline: date
    daily_minutes: int = Field(gt=0, le=600)
    notes: str | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1)
    level: str | None = Field(default=None, min_length=1)
    deadline: date | None = None
    daily_minutes: int | None = Field(default=None, gt=0, le=600)
    notes: str | None = None

