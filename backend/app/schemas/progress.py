from pydantic import BaseModel


class ProgressItem(BaseModel):
    goal_id: str
    goal_name: str
    total_tasks: int
    completed_tasks: int
    completion_rate: int
    today_total: int
    today_completed: int

