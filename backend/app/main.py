from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.routers import goals, materials, progress, tasks
from backend.app.services import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="AI-Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(goals.router, prefix="/api/goals", tags=["goals"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(progress.router, prefix="/api/progress", tags=["progress"])
app.include_router(materials.router, prefix="/api/materials", tags=["materials"])


@app.get("/")
def root():
    return {"message": "Welcome to the AI-Agent API!"}


@app.get("/api/health")
def health_check():
    return {"code": 0, "message": "success", "data": {"status": "ok"}}
