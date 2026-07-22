"""Endpoints de autenticacion (login/logout/setup/status). Publicos (no requieren sesion)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..auth import COOKIE_NAME
from ..logging_setup import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


def _set_cookie(response: Response, request: Request, token: str) -> None:
    secure = request.url.scheme == "https"
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", secure=secure, path="/",
        max_age=7 * 24 * 3600,
    )


@router.get("/status")
def status(request: Request):
    auth = request.app.state.auth
    token = request.cookies.get(COOKIE_NAME)
    user = auth.verify_session_token(token)
    return {
        "configured": auth.is_configured(),
        "authenticated": user is not None,
        "username": user,
        "auth_required": request.app.state.config.auth_required,
    }


@router.post("/setup")
def setup(body: Credentials, request: Request, response: Response):
    auth = request.app.state.auth
    if auth.is_configured():
        raise HTTPException(status_code=409, detail="La cuenta ya esta configurada. Inicia sesion.")
    try:
        auth.setup(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    token = auth.create_session_token(body.username)
    _set_cookie(response, request, token)
    audit("auth_setup", username=body.username)
    return {"ok": True, "username": body.username}


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    auth = request.app.state.auth
    if not auth.is_configured():
        raise HTTPException(status_code=409, detail="No hay cuenta configurada. Crea el administrador primero.")
    if not auth.verify_credentials(body.username, body.password):
        audit("auth_login_failed", username=body.username)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    token = auth.create_session_token(body.username)
    _set_cookie(response, request, token)
    audit("auth_login", username=body.username)
    return {"ok": True, "username": body.username}


@router.post("/logout")
def logout(request: Request, response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
