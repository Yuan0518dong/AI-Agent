import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.routers import agent, auth, goals, materials, progress, tasks
from backend.app.services import store


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "app"

# 本地开发默认允许 localhost:5500；部署时通过 CORS_ORIGINS 环境变量覆盖
# 示例：CORS_ORIGINS=* 或 CORS_ORIGINS=https://your-frontend.pages.dev
_cors_raw = os.getenv(
    "CORS_ORIGINS",
    "http://127.0.0.1:5500,http://localhost:5500,https://yuan0518dong.github.io",
)
CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS_ALLOW_ALL = CORS_ORIGINS == ["*"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init_db()
    yield


app = FastAPI(title="AI-Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.onrender\.com" if not CORS_ALLOW_ALL else None,
    allow_credentials=not CORS_ALLOW_ALL,
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
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health_check():
    return {"code": 0, "message": "success", "data": {"status": "ok"}}


# Keep API and docs routes above this catch-all mount. One uvicorn command now serves
# both the SPA assets and the FastAPI backend on the same origin.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
