"""Tests de la capa de base de datos: esquema, versionado, idempotencia."""
from db.database import BASE_SCHEMA_VERSION, MIGRATIONS, Database

# Version final esperada = la base + todas las migraciones incrementales aplicadas.
LATEST_VERSION = max([BASE_SCHEMA_VERSION, *MIGRATIONS.keys()])


def test_init_sets_version(tmp_path):
    d = Database(str(tmp_path / "v.db"))
    d.init()
    assert d.schema_version() == LATEST_VERSION


def test_init_idempotent(tmp_path):
    d = Database(str(tmp_path / "v.db"))
    d.init()
    d.init()  # no debe fallar ni cambiar la version
    assert d.schema_version() == LATEST_VERSION


def test_is_watched_column_present(tmp_path):
    # La migracion v2 agrega la columna is_watched (equipos "vigilados", Fase 3).
    d = Database(str(tmp_path / "v.db"))
    d.init()
    with d.connect() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(devices)").fetchall()}
    assert "is_watched" in cols


def test_tables_exist(tmp_path):
    d = Database(str(tmp_path / "v.db"))
    d.init()
    with d.connect() as c:
        names = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ("devices", "connection_events", "rules", "alerts", "settings"):
        assert t in names


def test_foreign_keys_enforced(tmp_path):
    import sqlite3
    d = Database(str(tmp_path / "v.db"))
    d.init()
    with d.connect() as c:
        try:
            c.execute("INSERT INTO connection_events (device_id, event_type, timestamp) "
                      "VALUES (99999, 'connected', '2026-01-01T00:00:00+00:00')")
            assert False, "deberia violar la FK"
        except sqlite3.IntegrityError:
            pass


def test_migration_applies_on_existing_db(tmp_path, monkeypatch):
    # Verifica que una nueva migracion se aplica sobre una BD ya inicializada.
    # Usamos una version por encima de las reales para no colisionar con ellas.
    import db.database as dbmod
    d = Database(str(tmp_path / "m.db"))
    d.init()
    assert d.schema_version() == LATEST_VERSION
    next_version = LATEST_VERSION + 1
    monkeypatch.setitem(dbmod.MIGRATIONS, next_version,
                        "ALTER TABLE devices ADD COLUMN notes TEXT;")
    d.init()
    assert d.schema_version() == next_version
    with d.connect() as c:
        cols = {r[1] for r in c.execute("PRAGMA table_info(devices)").fetchall()}
    assert "notes" in cols
