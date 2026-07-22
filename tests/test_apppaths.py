"""Tests de resolucion de rutas (modo codigo fuente)."""
import apppaths


def test_source_mode_paths_exist():
    assert apppaths.is_frozen() is False
    assert apppaths.dashboard_dir().is_dir()
    assert apppaths.oui_csv_path().is_file()
    assert apppaths.resource_path("db", "schema.sql").is_file()


def test_app_and_bundle_dir_equal_in_source():
    # En modo codigo fuente ambos apuntan a la raiz del proyecto
    assert apppaths.app_dir() == apppaths.bundle_dir()


def test_writable_dirs_created(tmp_path, monkeypatch):
    # data_dir / log_dir se crean si no existen
    assert apppaths.data_dir().is_dir()
    assert apppaths.log_dir().is_dir()
