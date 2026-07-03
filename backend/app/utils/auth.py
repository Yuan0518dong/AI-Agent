from fastapi import Header


def current_user_id(x_user_id: str | None = Header(default=None, alias="X-User-Id")) -> str | None:
    return x_user_id.strip() if x_user_id and x_user_id.strip() else None
