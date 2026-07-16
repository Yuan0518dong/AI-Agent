from fastapi import Cookie, HTTPException

from backend.app.services import auth_service


SESSION_COOKIE_NAME = "ai_agent_session"


def current_user_id(
    ai_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    user = auth_service.get_session_user_record(ai_agent_session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    return user["id"]


def current_user(
    ai_agent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> dict:
    user = auth_service.get_session_user_record(ai_agent_session)
    if not user:
        raise HTTPException(status_code=401, detail="请先登录后继续")
    return user
