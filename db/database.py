"""Conexion y ciclo de vida de la base de datos SQLite.

Diseño: conexiones de vida corta por operacion. SQLite en modo WAL soporta bien
multiples lectores concurrentes (la API) con un escritor (el servicio de escaneo),
que es exactamente el patron de esta aplicacion.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

# apppaths es un modulo de nivel raiz; garantizar que la raiz este en sys.path.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import apppaths  # noqa: E402

# schema.sql se resuelve via apppaths para funcionar tambien empaquetado (PyInstaller).
SCHEMA_PATH = apppaths.resource_path("db", "schema.sql")

# Versionado de esquema (M1). La version base (schema.sql) es la 1. Las futuras
# migraciones incrementales van en MIGRATIONS: {version: "SQL"} y se aplican en orden
# a las BD existentes. Se usa PRAGMA user_version para registrar el estado.
BASE_SCHEMA_VERSION = 1
MIGRATIONS: dict[int, str] = {
    # v2: marca de "vigilado" para alertar si un equipo importante se cae (Fase 3)
    2: "ALTER TABLE devices ADD COLUMN is_watched INTEGER NOT NULL DEFAULT 0;",
}


def default_db_path() -> Path:
    return apppaths.db_path()


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
        """Inicializa/migra el esquema (idempotente y versionado). [M1]

        - BD nueva (user_version=0): aplica schema.sql base y marca version 1.
        - BD existente: aplica las migraciones incrementales pendientes en orden.
        schema.sql usa CREATE TABLE IF NOT EXISTS, asi que re-ejecutarlo es seguro.
        """
        with self.connect() as conn:
            current = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current == 0:
                conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                conn.execute(f"PRAGMA user_version = {BASE_SCHEMA_VERSION}")
                current = BASE_SCHEMA_VERSION
            for version in sorted(MIGRATIONS):
                if version > current:
                    conn.executescript(MIGRATIONS[version])
                    conn.execute(f"PRAGMA user_version = {version}")
                    current = version

    def schema_version(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])

    def vacuum(self) -> None:
        with self.connect() as conn:
            conn.execute("VACUUM")
