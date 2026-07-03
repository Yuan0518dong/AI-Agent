from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIRouter

from backend.app.routers import agent, auth, goals, materials, progress, tasks
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


def include_api_router(router: APIRouter, prefix: str, tags: list[str]) -> None:
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        app.add_api_route(
            f"{prefix}{route.path}",
            route.endpoint,
            methods=list(route.methods or []),
            tags=tags,
            name=route.name,
            response_model=route.response_model,
            status_code=route.status_code,
            include_in_schema=route.include_in_schema,
        )


include_api_router(goals.router, prefix="/api/goals", tags=["goals"])
include_api_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
include_api_router(progress.router, prefix="/api/progress", tags=["progress"])
include_api_router(materials.router, prefix="/api/materials", tags=["materials"])
include_api_router(agent.router, prefix="/api/agent", tags=["agent"])
include_api_router(auth.router, prefix="/api/auth", tags=["auth"])


@app.get("/")
def root():
    return {"message": "Welcome to the AI-Agent API!"}


@app.get("/api/health")
def health_check():
    return {"code": 0, "message": "success", "data": {"status": "ok"}}
