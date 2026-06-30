from fastapi import FastAPI

from backend.app.routers import goals, progress, tasks


app = FastAPI(title="AI-Agent API", version="0.1.0")

app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(progress.router, prefix="/api/progress", tags=["progress"])


@app.get("/api/health")
def health_check():
    return {"code": 0, "message": "success", "data": {"status": "ok"}}

