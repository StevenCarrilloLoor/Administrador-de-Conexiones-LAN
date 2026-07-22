"""Tests de configuracion (env override, defaults, exposed_on_lan)."""
from api.config import Config


def test_defaults(monkeypatch):
    for k in ("LANMGR_HOST", "LANMGR_PORT", "LANMGR_AUTO_SCAN", "LANMGR_RETENTION_DAYS"):
        monkeypatch.delenv(k, raising=False)
    cfg = Config.load()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8080
    assert cfg.retention_days == 30
    assert cfg.exposed_on_lan is False


def test_env_override(monkeypatch):
    monkeypatch.setenv("LANMGR_HOST", "0.0.0.0")
    monkeypatch.setenv("LANMGR_PORT", "9000")
    monkeypatch.setenv("LANMGR_RETENTION_DAYS", "7")
    cfg = Config.load()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9000
    assert cfg.retention_days == 7
    assert cfg.exposed_on_lan is True


def test_auto_scan_parsing(monkeypatch):
    monkeypatch.setenv("LANMGR_AUTO_SCAN", "false")
    assert Config.load().auto_scan is False
    monkeypatch.setenv("LANMGR_AUTO_SCAN", "si")
    assert Config.load().auto_scan is True
