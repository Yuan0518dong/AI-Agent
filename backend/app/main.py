import os
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute, APIRouter
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.routers import agent, auth, goals, materials, progress, tasks
from backend.app.services import rate_limit_service, store


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "app"

_cors_raw = os.getenv("CORS_ORIGINS", "http://127.0.0.1:8001,http://localhost:8001")
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in _cors_raw.split(",") if origin.strip()]
if "*" in CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS must be an explicit allowlist; '*' is not permitted.")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    rate_limit_service.require_runtime_security_configuration()
    store.init_db()
    yield


app = FastAPI(title="AI-Agent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-Id"],
)


@app.middleware("http")
async def add_request_context_and_validate_origin(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = request_id
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        origin = request.headers.get("Origin")
        if origin and not _is_allowed_origin(request, origin):
            return _error_response(
                request,
                status_code=403,
                error_type="origin_forbidden",
                message="请求来源未获允许",
            )
        if not origin and _app_env() == "production":
            return _error_response(
                request,
                status_code=403,
                error_type="origin_required",
                message="生产环境写请求必须提供同源 Origin",
            )
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled API error request_id=%s", request_id)
        response = _error_response(
            request,
            status_code=500,
            error_type="internal_error",
            message="服务暂时不可用，请稍后重试",
        )
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException):
    error_type = {
        400: "bad_request",
        401: "auth_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }.get(exc.status_code, "http_error")
    headers = dict(exc.headers or {})
    return _error_response(
        request,
        status_code=exc.status_code,
        error_type=error_type,
        message=str(exc.detail),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(request: Request, exc: RequestValidationError):
    field_errors = {
        ".".join(str(part) for part in error["loc"] if part != "body"): error["msg"]
        for error in exc.errors()
    }
    return _error_response(
        request,
        status_code=422,
        error_type="validation_error",
        message="请求参数不合法",
        field_errors=field_errors,
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception):
    logger.exception("Unhandled API error request_id=%s", getattr(request.state, "request_id", ""))
    return _error_response(
        request,
        status_code=500,
        error_type="internal_error",
        message="服务暂时不可用，请稍后重试",
    )


def _is_allowed_origin(request: Request, origin: str) -> bool:
    normalized_origin = origin.rstrip("/")
    return normalized_origin in CORS_ORIGINS


def _app_env() -> str:
    return os.getenv("APP_ENV", "development").strip().lower()


def _error_response(
    request: Request,
    *,
    status_code: int,
    error_type: str,
    message: str,
    field_errors: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = {"X-Request-Id": getattr(request.state, "request_id", "")}
    response_headers.update(headers or {})
    return JSONResponse(
        status_code=status_code,
        headers=response_headers,
        content={
            "error": {
                "type": error_type,
                "message": message,
                "fieldErrors": field_errors or {},
            },
            "requestId": getattr(request.state, "request_id", ""),
        },
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


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
def api_not_found(path: str):
    raise HTTPException(status_code=404, detail="API endpoint not found")


# Keep API and docs routes above this catch-all mount. One uvicorn command now serves
# both the SPA assets and the FastAPI backend on the same origin.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
