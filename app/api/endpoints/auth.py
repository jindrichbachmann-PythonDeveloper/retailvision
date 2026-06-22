# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.auth_service import (
    forgot_password,
    reset_password,
    register_user,
    token_login,
    login_user,
)
from app.api.deps.auth import get_current_user, require_admin

router = APIRouter()


# --------- MODELY (1:1) ---------
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class ForgotRequest(BaseModel):
    email: str


class ResetRequest(BaseModel):
    token: str
    new_password: str


# --------- ENDPOINTY (1:1) ---------
@router.post("/api/auth/forgot", response_class=JSONResponse)
def api_forgot_password(data: ForgotRequest):
    return forgot_password(data.email)


@router.post("/api/auth/reset", response_class=JSONResponse)
def api_reset_password(data: ResetRequest):
    return reset_password(data.token, data.new_password)


@router.post("/api/auth/register", response_class=JSONResponse)
def api_register(data: RegisterRequest):
    return register_user(data.username, data.password)


@router.post("/api/auth/token", response_class=JSONResponse)
def api_token(data: TokenRequest):
    return token_login(data.username, data.password)


@router.post("/api/auth/login", response_class=JSONResponse)
def api_login(data: LoginRequest):
    return login_user(data.username, data.password)


@router.get("/api/me", response_class=JSONResponse)
def api_me(user: dict = Depends(get_current_user)):
    return {
        "ok": True,
        "user": user,
    }


@router.get("/api/admin/me", response_class=JSONResponse)
def api_admin_me(user: dict = Depends(require_admin)):
    return {
        "ok": True,
        "user": user,
    }