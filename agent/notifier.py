"""Notificaciones desacopladas (Fase 3).

Interfaz `Notifier` con tres backends: Telegram, email (SMTP) y ntfy. Un
`NotificationManager` lee la configuracion desde `settings` y difunde el aviso a
todos los backends habilitados. Se dispara en alertas (dispositivo nuevo, caida).

La configuracion se guarda en la tabla `settings` con el prefijo `notif_`.
"""
from __future__ import annotations

import logging
import smtplib
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from typing import Optional

log = logging.getLogger("lanmanager.notifier")


def _as_bool(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on", "si")


class Notifier(ABC):
    name = "base"

    @abstractmethod
    def send(self, title: str, message: str) -> tuple[bool, str]:
        ...


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def send(self, title: str, message: str) -> tuple[bool, str]:
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            text = f"*{title}*\n{message}"
            r = requests.post(url, json={"chat_id": self.chat_id, "text": text,
                                         "parse_mode": "Markdown"}, timeout=10)
            return (r.ok, f"HTTP {r.status_code}")
        except Exception as exc:
            return (False, str(exc))


class NtfyNotifier(Notifier):
    name = "ntfy"

    def __init__(self, server: str, topic: str):
        self.server = (server or "https://ntfy.sh").rstrip("/")
        self.topic = topic

    def send(self, title: str, message: str) -> tuple[bool, str]:
        try:
            import requests
            r = requests.post(f"{self.server}/{self.topic}",
                              data=message.encode("utf-8"),
                              headers={"Title": title.encode("utf-8")}, timeout=10)
            return (r.ok, f"HTTP {r.status_code}")
        except Exception as exc:
            return (False, str(exc))


class SmtpNotifier(Notifier):
    name = "email"

    def __init__(self, host: str, port: int, user: str, password: str,
                 sender: str, recipient: str, use_tls: bool = True):
        self.host = host
        self.port = int(port or 587)
        self.user = user
        self.password = password
        self.sender = sender or user
        self.recipient = recipient
        self.use_tls = use_tls

    def send(self, title: str, message: str) -> tuple[bool, str]:
        try:
            msg = MIMEText(message, _charset="utf-8")
            msg["Subject"] = title
            msg["From"] = self.sender
            msg["To"] = self.recipient
            with smtplib.SMTP(self.host, self.port, timeout=15) as s:
                if self.use_tls:
                    s.starttls()
                if self.user:
                    s.login(self.user, self.password)
                s.sendmail(self.sender, [self.recipient], msg.as_string())
            return (True, "enviado")
        except Exception as exc:
            return (False, str(exc))


class NotificationManager:
    """Construye los backends desde settings y difunde a todos los habilitados."""

    def __init__(self, settings):
        self.settings = settings

    def _cfg(self, key: str, default: str = "") -> str:
        return self.settings.get(f"notif_{key}", default)

    def backends(self) -> list[Notifier]:
        out: list[Notifier] = []
        if _as_bool(self._cfg("telegram_enabled")):
            tok, chat = self._cfg("telegram_token"), self._cfg("telegram_chat_id")
            if tok and chat:
                out.append(TelegramNotifier(tok, chat))
        if _as_bool(self._cfg("ntfy_enabled")):
            topic = self._cfg("ntfy_topic")
            if topic:
                out.append(NtfyNotifier(self._cfg("ntfy_server", "https://ntfy.sh"), topic))
        if _as_bool(self._cfg("smtp_enabled")):
            host, to = self._cfg("smtp_host"), self._cfg("smtp_to")
            if host and to:
                out.append(SmtpNotifier(
                    host, self._cfg("smtp_port", "587"), self._cfg("smtp_user"),
                    self._cfg("smtp_password"), self._cfg("smtp_from"), to,
                    _as_bool(self._cfg("smtp_tls", "true")),
                ))
        return out

    @property
    def enabled(self) -> bool:
        return len(self.backends()) > 0

    def notify(self, title: str, message: str) -> list[dict]:
        """Envia a todos los backends habilitados. Nunca lanza; loguea fallos."""
        results = []
        for b in self.backends():
            try:
                ok, detail = b.send(title, message)
            except Exception as exc:  # pragma: no cover
                ok, detail = False, str(exc)
            if not ok:
                log.warning("Notificacion via %s fallo: %s", b.name, detail)
            results.append({"backend": b.name, "ok": ok, "detail": detail})
        return results

    def public_config(self) -> dict:
        """Config sin secretos, para mostrar en el dashboard."""
        return {
            "telegram": {"enabled": _as_bool(self._cfg("telegram_enabled")),
                         "chat_id": self._cfg("telegram_chat_id")},
            "ntfy": {"enabled": _as_bool(self._cfg("ntfy_enabled")),
                     "server": self._cfg("ntfy_server", "https://ntfy.sh"),
                     "topic": self._cfg("ntfy_topic")},
            "email": {"enabled": _as_bool(self._cfg("smtp_enabled")),
                      "host": self._cfg("smtp_host"), "to": self._cfg("smtp_to")},
        }
