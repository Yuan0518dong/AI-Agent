from fastapi import FastAPI

from backend.app.routers import goals, progress, tasks
from backend.app.services import store


app = FastAPI(title="AI-Agent API", version="0.1.0")

app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(progress.router, prefix="/api/progress", tags=["progress"])


@app.on_event("startup")
def startup():
    store.init_db()


@app.get("/")
def root():
    return {"message": "Welcome to the AI-Agent API!"}


@app.get("/api/health")
def health_check():
    return {"code": 0, "message": "success", "data": {"status": "ok"}}

