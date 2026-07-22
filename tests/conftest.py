"""Fixtures compartidas de la suite de tests.

Ninguna prueba requiere Npcap ni una LAN real: el escaneo se mockea. Asi la suite
corre igual en Windows, Linux y en CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def db(tmp_path):
    from db.database import Database
    d = Database(str(tmp_path / "test.db"))
    d.init()
    return d


@pytest.fixture
def repos(db):
    from db.repositories import (
        AlertRepository, ConnectionEventRepository, DeviceRepository,
        RuleRepository, SettingsRepository,
    )
    return {
        "dev": DeviceRepository(db),
        "ev": ConnectionEventRepository(db),
        "al": AlertRepository(db),
        "rule": RuleRepository(db),
        "set": SettingsRepository(db),
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App FastAPI con BD y logs temporales, sin auto-escaneo."""
    monkeypatch.setenv("LANMGR_AUTO_SCAN", "false")
    monkeypatch.setenv("LANMGR_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("LANMGR_LOG_DIR", str(tmp_path / "logs"))
    from api.app import create_app
    from api.config import Config
    return create_app(Config.load())


@pytest.fixture
async def client(app):
    """Cliente HTTP en proceso (httpx ASGITransport), sin abrir puertos."""
    import httpx
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def seed():
    """Devuelve una funcion para sembrar dispositivos via el repositorio de la app."""
    def _seed(app, mac="AA:BB:CC:00:11:22", ip="192.168.1.10", hostname="host",
              vendor="Cisco Systems, Inc", dtype="Red (Cisco)", random_mac=False):
        return app.state.device_repo.upsert_seen(
            mac=mac, ip=ip, hostname=hostname, vendor=vendor,
            device_type=dtype, is_random_mac=random_mac,
        )
    return _seed
