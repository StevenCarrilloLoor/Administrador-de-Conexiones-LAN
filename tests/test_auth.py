"""Tests de autenticacion: hashing, sesiones, setup, login y proteccion de rutas."""
from api.auth import AuthService, hash_password, verify_password


def test_password_hashing_roundtrip():
    h = hash_password("Secreta123")
    assert verify_password("Secreta123", h) is True
    assert verify_password("otra", h) is False
    assert h != hash_password("Secreta123")  # salt distinto


def test_authservice_setup_and_session(repos):
    auth = AuthService(repos["set"])
    assert auth.is_configured() is False
    auth.setup("steven", "clave123")
    assert auth.is_configured() is True
    assert auth.verify_credentials("steven", "clave123") is True
    assert auth.verify_credentials("steven", "mala") is False
    tok = auth.create_session_token("steven")
    assert auth.verify_session_token(tok) == "steven"
    assert auth.verify_session_token(tok + "x") is None
    assert auth.verify_session_token(None) is None


def test_setup_validation(repos):
    auth = AuthService(repos["set"])
    import pytest
    with pytest.raises(ValueError):
        auth.setup("ab", "clave123")       # usuario corto
    with pytest.raises(ValueError):
        auth.setup("steven", "123")        # clave corta


# --- Proteccion de rutas por HTTP (app con auth requerida) ---
async def test_protected_without_session(client_auth):
    # sin sesion, la API responde 401
    assert (await client_auth.get("/api/devices")).status_code == 401
    # la raiz redirige a /login
    r = await client_auth.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/login"


async def test_status_is_public(client_auth):
    r = await client_auth.get("/api/auth/status")
    assert r.status_code == 200
    assert r.json()["configured"] is False


async def test_setup_then_access(client_auth):
    # primer uso: crear cuenta
    r = await client_auth.post("/api/auth/setup", json={"username": "admin", "password": "clave123"})
    assert r.status_code == 200
    # ya no se puede volver a hacer setup
    r2 = await client_auth.post("/api/auth/setup", json={"username": "x", "password": "clave123"})
    assert r2.status_code == 409
    # con la cookie de sesion (httpx la guarda), la API responde
    assert (await client_auth.get("/api/devices")).status_code == 200


async def test_login_flow(client_auth):
    await client_auth.post("/api/auth/setup", json={"username": "admin", "password": "clave123"})
    await client_auth.post("/api/auth/logout")
    bad = await client_auth.post("/api/auth/login", json={"username": "admin", "password": "mala"})
    assert bad.status_code == 401
    ok = await client_auth.post("/api/auth/login", json={"username": "admin", "password": "clave123"})
    assert ok.status_code == 200
    assert (await client_auth.get("/api/devices")).status_code == 200
