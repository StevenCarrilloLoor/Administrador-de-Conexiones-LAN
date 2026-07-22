"""Tests del bootstrap de Npcap (parseo de URL y verificacion de firma)."""
import os

from agent import npcap_bootstrap as nb


def test_latest_installer_url_parses_highest(monkeypatch):
    html = ("<a href='npcap-1.79.exe'>x</a>"
            "<a href='npcap-1.88.exe'>x</a>"
            "<a href='npcap-1.80.exe'>x</a>")

    class FakeResp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return html.encode("utf-8")

    monkeypatch.setattr(nb.urllib.request, "urlopen", lambda *a, **k: FakeResp())
    assert nb.latest_installer_url() == "https://npcap.com/dist/npcap-1.88.exe"


def test_latest_installer_url_fallback_on_error(monkeypatch):
    def boom(*a, **k):
        raise OSError("sin red")
    monkeypatch.setattr(nb.urllib.request, "urlopen", boom)
    assert nb.latest_installer_url() == nb.FALLBACK_INSTALLER_URL


def test_verify_signature_skips_on_non_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    ok, detail = nb.verify_installer_signature("/tmp/whatever.exe")
    assert ok is True
    assert "omit" in detail.lower()
