"""Tests del launcher: guarda de streams None (el crash del .exe windowed)."""
import sys

import apppaths
import launcher


def test_ensure_std_streams_replaces_none(monkeypatch, tmp_path):
    # Simula el .exe windowed: sys.stdout/stderr = None
    monkeypatch.setattr(apppaths, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    launcher.ensure_std_streams()

    assert sys.stdout is not None
    assert sys.stderr is not None
    # Deben tener isatty() (lo que consulta uvicorn) y ser escribibles
    assert sys.stdout.isatty() is False
    sys.stdout.write("prueba\n")
    sys.stdout.flush()


def test_ensure_std_streams_noop_when_present(monkeypatch):
    # Si ya hay streams, no los toca
    before_out, before_err = sys.stdout, sys.stderr
    launcher.ensure_std_streams()
    assert sys.stdout is before_out
    assert sys.stderr is before_err
