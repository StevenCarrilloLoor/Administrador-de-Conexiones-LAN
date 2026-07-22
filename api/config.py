"""Configuracion de la aplicacion.

Prioridad: variables de entorno (LANMGR_*) > config.ini > valores por defecto.
Las rutas se anclan a la raiz del proyecto para funcionar sin importar el CWD.
"""
from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "config.ini"


def _get(cfg, section, key, fallback):
    env_key = f"LANMGR_{key.upper()}"
    if env_key in os.environ:
        return os.environ[env_key]
    if cfg.has_option(section, key):
        return cfg.get(section, key)
    return fallback


@dataclass
class Config:
    host: str = "127.0.0.1"
    port: int = 8080
    scan_interval: int = 30
    online_ttl: int = 90
    scan_timeout: float = 3.0
    auto_scan: bool = True
    db_path: str = str(ROOT / "data" / "lanmanager.db")
    log_dir: str = str(ROOT / "logs")
    dashboard_dir: str = str(ROOT / "dashboard")

    @classmethod
    def load(cls) -> "Config":
        cfg = configparser.ConfigParser()
        if CONFIG_FILE.exists():
            cfg.read(CONFIG_FILE, encoding="utf-8")
        for sec in ("server", "scan"):
            if not cfg.has_section(sec):
                cfg.add_section(sec)

        def as_bool(v) -> bool:
            return str(v).strip().lower() in ("1", "true", "yes", "on", "si")

        return cls(
            host=_get(cfg, "server", "host", "127.0.0.1"),
            port=int(_get(cfg, "server", "port", 8080)),
            scan_interval=int(_get(cfg, "scan", "interval", 30)),
            online_ttl=int(_get(cfg, "scan", "online_ttl", 90)),
            scan_timeout=float(_get(cfg, "scan", "timeout", 3.0)),
            auto_scan=as_bool(_get(cfg, "scan", "auto_scan", "true")),
            db_path=_get(cfg, "server", "db_path", str(ROOT / "data" / "lanmanager.db")),
            log_dir=_get(cfg, "server", "log_dir", str(ROOT / "logs")),
            dashboard_dir=str(ROOT / "dashboard"),
        )

    @property
    def exposed_on_lan(self) -> bool:
        return self.host not in ("127.0.0.1", "localhost", "::1")
