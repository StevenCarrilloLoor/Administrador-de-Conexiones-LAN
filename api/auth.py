"""Autenticacion del panel (Fase 3).

- Contraseñas con bcrypt (hash + salt).
- Sesion por cookie firmada con HMAC-SHA256 (stdlib), con expiracion.
- Credenciales y clave de firma persistidas en la tabla `settings`.

Requisito de la especificacion: el dashboard queda expuesto en la red, asi que la
autenticacion es obligatoria antes de exponerlo (no opcional).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional

try:
    import bcrypt  # hashing de contraseñas
    _HAS_BCRYPT = True
except Exception:  # pragma: no cover - fallback si bcrypt no esta disponible
    _HAS_BCRYPT = False

from db.repositories import SettingsRepository

COOKIE_NAME = "acl_session"
_DEFAULT_TTL = 7 * 24 * 3600  # 7 dias

# Claves en settings
_K_USER = "auth_username"
_K_HASH = "auth_password_hash"
_K_SECRET = "auth_secret"


# --------------------------------------------------------------------------- #
# Hashing de contraseñas
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    if _HAS_BCRYPT:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    # Fallback stdlib (PBKDF2) por si bcrypt no esta presente en el entorno.
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return "pbkdf2$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2$"):
            _, salt_b64, hash_b64 = stored.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(hash_b64)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
            return hmac.compare_digest(dk, expected)
        if _HAS_BCRYPT:
            return bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Servicio de autenticacion (sesiones firmadas)
# --------------------------------------------------------------------------- #
class AuthService:
    def __init__(self, settings: SettingsRepository):
        self.settings = settings

    # -- estado --
    def is_configured(self) -> bool:
        return bool(self.settings.get(_K_USER))

    def username(self) -> Optional[str]:
        return self.settings.get(_K_USER)

    def _secret(self) -> bytes:
        sec = self.settings.get(_K_SECRET)
        if not sec:
            sec = secrets.token_hex(32)
            self.settings.set(_K_SECRET, sec)
        return sec.encode("utf-8")

    # -- alta / verificacion --
    def setup(self, username: str, password: str) -> None:
        """Crea la cuenta admin. Solo permitido si aun no hay ninguna configurada."""
        if self.is_configured():
            raise ValueError("La cuenta de administrador ya esta configurada.")
        username = (username or "").strip()
        if len(username) < 3:
            raise ValueError("El usuario debe tener al menos 3 caracteres.")
        if len(password or "") < 6:
            raise ValueError("La contraseña debe tener al menos 6 caracteres.")
        self.settings.set(_K_USER, username)
        self.settings.set(_K_HASH, hash_password(password))
        self._secret()  # generar clave de firma

    def change_password(self, old_password: str, new_password: str) -> None:
        if not self.verify_credentials(self.username() or "", old_password):
            raise ValueError("La contraseña actual no coincide.")
        if len(new_password or "") < 6:
            raise ValueError("La nueva contraseña debe tener al menos 6 caracteres.")
        self.settings.set(_K_HASH, hash_password(new_password))

    def verify_credentials(self, username: str, password: str) -> bool:
        stored_user = self.settings.get(_K_USER)
        stored_hash = self.settings.get(_K_HASH)
        if not stored_user or not stored_hash:
            return False
        if not hmac.compare_digest((username or "").strip(), stored_user):
            return False
        return verify_password(password, stored_hash)

    # -- sesiones (cookie firmada) --
    def create_session_token(self, username: str, ttl: int = _DEFAULT_TTL) -> str:
        payload = {"u": username, "exp": int(time.time()) + int(ttl)}
        raw = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        sig = hmac.new(self._secret(), raw.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{raw}.{sig}"

    def verify_session_token(self, token: Optional[str]) -> Optional[str]:
        if not token or "." not in token:
            return None
        try:
            raw, sig = token.rsplit(".", 1)
            expected = hmac.new(self._secret(), raw.encode("utf-8"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return None
            payload = json.loads(base64.urlsafe_b64decode(raw.encode("utf-8")))
            if int(payload.get("exp", 0)) < int(time.time()):
                return None
            return payload.get("u")
        except Exception:
            return None
