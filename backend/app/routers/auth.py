from fastapi import APIRouter, HTTPException

from backend.app.schemas.auth import LoginRequest, RegisterRequest
from backend.app.services import auth_service
from backend.app.utils.responses import ok


router = APIRouter()


@router.post("/register")
def register(payload: RegisterRequest):
    user = auth_service.create_user(payload.name, payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=409, detail="Email already registered")
    return ok(user)


@router.post("/login")
def login(payload: LoginRequest):
    user = auth_service.authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return ok(user)
