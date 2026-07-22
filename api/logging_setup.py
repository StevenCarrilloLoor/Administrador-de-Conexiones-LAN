"""Logging estructurado a archivo (requisito 7.3).

Dos destinos:
  * app.log    -> log general de la aplicacion (rotativo)
  * audit.log  -> auditoria de acciones sensibles (bloqueo/desbloqueo/limite),
                  con marca de tiempo, en formato clave=valor facil de parsear.
Ambos tambien salen por consola (si hay consola disponible).
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_AUDIT_LOGGER = "lanmanager.audit"
# Marca los handlers que instala ESTE modulo, para no borrar handlers ajenos
# (p. ej. el de launcher.log que agrega el launcher). [B3]
_OWNED = "_lanmgr_owned"


def _console_handler(fmt: logging.Formatter):
    """StreamHandler solo si hay un stream real (en el .exe windowed stderr puede ser None). [M5]"""
    stream = sys.stderr if sys.stderr is not None else sys.stdout
    if stream is None:
        return None
    h = logging.StreamHandler(stream)
    h.setFormatter(fmt)
    setattr(h, _OWNED, True)
    return h


def _clear_owned(logger: logging.Logger) -> None:
    for h in list(logger.handlers):
        if getattr(h, _OWNED, False):
            logger.removeHandler(h)


def setup_logging(log_dir: str, level: int = logging.INFO) -> None:
    d = Path(log_dir)
    d.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    root = logging.getLogger("lanmanager")
    root.setLevel(level)
    _clear_owned(root)  # NO borra handlers de terceros (launcher.log)

    app_file = RotatingFileHandler(d / "app.log", maxBytes=2_000_000,
                                   backupCount=5, encoding="utf-8")
    app_file.setFormatter(fmt)
    setattr(app_file, _OWNED, True)
    root.addHandler(app_file)

    console = _console_handler(fmt)
    if console is not None:
        root.addHandler(console)

    # Auditoria: archivo dedicado, no propaga al root para no duplicar
    audit = logging.getLogger(_AUDIT_LOGGER)
    audit.setLevel(logging.INFO)
    audit.propagate = False
    _clear_owned(audit)
    audit_file = RotatingFileHandler(d / "audit.log", maxBytes=2_000_000,
                                     backupCount=10, encoding="utf-8")
    audit_file.setFormatter(logging.Formatter("%(message)s"))
    setattr(audit_file, _OWNED, True)
    audit.addHandler(audit_file)
    ac = _console_handler(logging.Formatter("%(message)s"))
    if ac is not None:
        audit.addHandler(ac)


def audit(action: str, **fields) -> None:
    """Registra una accion auditable en formato clave=valor."""
    ts = datetime.now(timezone.utc).isoformat()
    parts = [f"ts={ts}", f"action={action}"]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    logging.getLogger(_AUDIT_LOGGER).info(" ".join(parts))
