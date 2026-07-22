"""Configuracion de la aplicacion.

Prioridad: variables de entorno (LANMGR_*) > config.ini > valores por defecto.
Las rutas se resuelven via apppaths para funcionar igual como codigo fuente
(`python main.py`) y como ejecutable empaquetado (AdministradorLAN.exe).
"""
from __future__ import annotations

import configparser
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# apppaths es un modulo de nivel raiz; garantizar que la raiz este en sys.path.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import apppaths  # noqa: E402

CONFIG_FILE = apppaths.config_file()


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
    retention_days: int = 30
    db_path: str = field(default_factory=lambda: str(apppaths.db_path()))
    log_dir: str = field(default_factory=lambda: str(apppaths.log_dir()))
    dashboard_dir: str = field(default_factory=lambda: str(apppaths.dashboard_dir()))

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
            retention_days=int(_get(cfg, "scan", "retention_days", 30)),
            db_path=_get(cfg, "server", "db_path", str(apppaths.db_path())),
            log_dir=_get(cfg, "server", "log_dir", str(apppaths.log_dir())),
            dashboard_dir=str(apppaths.dashboard_dir()),
        )

    @property
    def exposed_on_lan(self) -> bool:
        return self.host not in ("127.0.0.1", "localhost", "::1")
