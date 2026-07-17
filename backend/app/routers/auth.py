import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from backend.app.schemas.auth import AccountDeleteRequest, LoginRequest, RegisterRequest
from backend.app.services import account_data_service, auth_service, demo_service, rate_limit_service, store
from backend.app.utils.auth import SESSION_COOKIE_NAME, current_user
from backend.app.utils.responses import ok


router = APIRouter()


@router.post("/register")
def register(payload: RegisterRequest, request: Request, response: Response):
    rate_limit_service.consume_ip_limit(
        request,
        "auth_register",
        limit_env="REGISTER_IP_HOURLY_LIMIT",
        default_limit=5,
        window_seconds=60 * 60,
    )
    user = auth_service.create_user(payload.name, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    # The public payload intentionally omits IDs; resolve the internal user only on the server.
    internal_user = store.get_user_by_email(user["email"])
    if not internal_user:
        raise HTTPException(status_code=500, detail="账号创建后无法读取")
    token = auth_service.create_session(internal_user["id"])
    _set_session_cookie(response, token, demo=False)
    return ok(user)


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response):
    rate_limit_service.consume_ip_limit(
        request,
        "auth_login",
        limit_env="LOGIN_IP_15_MINUTE_LIMIT",
        default_limit=20,
        window_seconds=15 * 60,
    )
    user = auth_service.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    internal_user = store.get_user_by_email(user["email"])
    if not internal_user:
        raise HTTPException(status_code=401, detail="登录会话已失效")
    token = auth_service.create_session(internal_user["id"])
    _set_session_cookie(response, token, demo=False)
    return ok(user)


@router.get("/me")
def me(user: dict = Depends(current_user)):
    return ok(auth_service.public_user(user))


@router.post("/logout")
def logout(
    response: Response,
    ai_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    auth_service.revoke_session(ai_agent_session)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return ok({"loggedOut": True})


@router.get("/export")
def export_account_data(user: dict = Depends(current_user)):
    return ok(account_data_service.export_account_data(user))


@router.delete("/account")
def delete_account(
    payload: AccountDeleteRequest,
    response: Response,
    user: dict = Depends(current_user),
):
    if not account_data_service.delete_account_data(user["id"]):
        raise HTTPException(status_code=404, detail="账号不存在")
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return ok({"deleted": True})


@router.post("/demo")
def demo(request: Request, response: Response):
    rate_limit_service.consume_ip_limit(
        request,
        "auth_demo",
        limit_env="DEMO_IP_HOURLY_LIMIT",
        default_limit=5,
        window_seconds=60 * 60,
    )
    user, token = demo_service.create_demo_session()
    _set_session_cookie(response, token, demo=True)
    return ok(user)


def _set_session_cookie(response: Response, token: str, *, demo: bool) -> None:
    max_age = 60 * 60 * (auth_service.DEMO_SESSION_HOURS if demo else auth_service.REGISTERED_SESSION_DAYS * 24)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_is_production(),
        path="/",
    )


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() == "production"
