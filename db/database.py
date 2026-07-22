"""Conexion y ciclo de vida de la base de datos SQLite.

Diseño: conexiones de vida corta por operacion. SQLite en modo WAL soporta bien
multiples lectores concurrentes (la API) con un escritor (el servicio de escaneo),
que es exactamente el patron de esta aplicacion.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def default_db_path() -> Path:
    data_dir = _PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "lanmanager.db"


class Database:
    """Envoltorio delgado sobre sqlite3 con inicializacion de esquema."""

    def __init__(self, path: str | Path | None = None):
        self.path = str(path or default_db_path())

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        """Crea el esquema si no existe (idempotente)."""
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(sql)

    def vacuum(self) -> None:
        with self.connect() as conn:
            conn.execute("VACUUM")
