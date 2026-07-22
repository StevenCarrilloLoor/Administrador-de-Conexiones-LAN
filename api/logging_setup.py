"""Logging estructurado a archivo (requisito 7.3).

Dos destinos:
  * app.log    -> log general de la aplicacion (rotativo)
  * audit.log  -> auditoria de acciones sensibles (bloqueo/desbloqueo/limite),
                  con marca de tiempo, en formato clave=valor facil de parsear.
Ambos tambien salen por consola.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_AUDIT_LOGGER = "lanmanager.audit"


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger("lanmanager")
    root.setLevel(level)
    root.handlers.clear()

    app_file = RotatingFileHandler(d / "app.log", maxBytes=2_000_000,
                                   backupCount=5, encoding="utf-8")
    app_file.setFormatter(fmt)
    root.addHandler(app_file)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    # Auditoria: archivo dedicado, no propaga al root para no duplicar
    audit = logging.getLogger(_AUDIT_LOGGER)
    audit.setLevel(logging.INFO)
    audit.handlers.clear()
    audit.propagate = False
    audit_file = RotatingFileHandler(d / "audit.log", maxBytes=2_000_000,
                                     backupCount=10, encoding="utf-8")
    audit_file.setFormatter(logging.Formatter("%(message)s"))
    audit.addHandler(audit_file)
    audit.addHandler(console)


def audit(action: str, **fields) -> None:
    """Registra una accion auditable en formato clave=valor."""
    ts = datetime.now(timezone.utc).isoformat()
    parts = [f"ts={ts}", f"action={action}"]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    logging.getLogger(_AUDIT_LOGGER).info(" ".join(parts))
