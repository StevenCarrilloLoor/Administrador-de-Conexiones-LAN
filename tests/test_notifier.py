"""Tests del gestor de notificaciones (Fase 3), con los backends mockeados."""
from agent.notifier import (
    NotificationManager,
    NtfyNotifier,
    SmtpNotifier,
    TelegramNotifier,
    _as_bool,
)
from db.repositories import SettingsRepository


def test_as_bool():
    assert _as_bool("true") and _as_bool("1") and _as_bool("si") and _as_bool("on")
    assert not _as_bool("false") and not _as_bool("0") and not _as_bool("")


def test_manager_disabled_by_default(db):
    nm = NotificationManager(SettingsRepository(db))
    assert nm.enabled is False
    assert nm.backends() == []
    # notify() no falla aunque no haya backends
    assert nm.notify("t", "m") == []


def test_backends_built_from_settings(db):
    s = SettingsRepository(db)
    s.set("notif_telegram_enabled", "true")
    s.set("notif_telegram_token", "123:ABC")
    s.set("notif_telegram_chat_id", "999")
    s.set("notif_ntfy_enabled", "true")
    s.set("notif_ntfy_topic", "mi-red")
    nm = NotificationManager(s)
    names = {b.name for b in nm.backends()}
    assert names == {"telegram", "ntfy"}
    assert nm.enabled is True


def test_backend_incomplete_is_skipped(db):
    s = SettingsRepository(db)
    s.set("notif_telegram_enabled", "true")  # sin token ni chat_id
    nm = NotificationManager(s)
    assert nm.backends() == []


def test_public_config_hides_secrets(db):
    s = SettingsRepository(db)
    s.set("notif_telegram_enabled", "true")
    s.set("notif_telegram_token", "SECRETO")
    s.set("notif_telegram_chat_id", "999")
    cfg = NotificationManager(s).public_config()
    # el token NO debe aparecer en la config publica
    assert "SECRETO" not in str(cfg)
    assert cfg["telegram"]["chat_id"] == "999"


def test_notify_aggregates_backend_results(db, monkeypatch):
    s = SettingsRepository(db)
    s.set("notif_ntfy_enabled", "true")
    s.set("notif_ntfy_topic", "t")
    nm = NotificationManager(s)
    monkeypatch.setattr(NtfyNotifier, "send", lambda self, t, m: (True, "HTTP 200"))
    res = nm.notify("titulo", "cuerpo")
    assert res == [{"backend": "ntfy", "ok": True, "detail": "HTTP 200"}]


def test_notify_survives_backend_exception(db, monkeypatch):
    s = SettingsRepository(db)
    s.set("notif_ntfy_enabled", "true")
    s.set("notif_ntfy_topic", "t")
    nm = NotificationManager(s)

    def boom(self, t, m):
        raise RuntimeError("sin red")
    monkeypatch.setattr(NtfyNotifier, "send", boom)
    res = nm.notify("t", "m")
    assert res[0]["ok"] is False  # no propaga la excepcion


def test_telegram_send_builds_request(monkeypatch):
    calls = {}

    class FakeResp:
        ok = True
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        calls["url"] = url
        calls["json"] = json
        return FakeResp()

    # send() hace `import requests` internamente; inyectamos un modulo falso
    # via sys.modules (monkeypatch.setitem lo restaura al terminar el test).
    import sys
    fake_requests = type("R", (), {"post": staticmethod(fake_post)})
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    ok, detail = TelegramNotifier("123:ABC", "999").send("Hola", "Mundo")
    assert ok is True
    assert "bot123:ABC/sendMessage" in calls["url"]
    assert calls["json"]["chat_id"] == "999"
