"""Tests de resolucion de fabricante por OUI."""
from agent.oui import (
    OUILookup, is_locally_administered, normalize_mac, oui_prefix, shared_lookup,
)


def test_normalize_mac_variants():
    assert normalize_mac("b8-27-eb-11-22-33") == "B8:27:EB:11:22:33"
    assert normalize_mac("b827eb112233") == "B8:27:EB:11:22:33"
    assert normalize_mac("B8:27:EB:11:22:33") == "B8:27:EB:11:22:33"


def test_oui_prefix():
    assert oui_prefix("b8:27:eb:11:22:33") == "B827EB"


def test_locally_administered_bit():
    # bit U/L (2do bit menos significativo del primer octeto)
    assert is_locally_administered("02:00:00:00:00:00") is True
    assert is_locally_administered("FA:11:22:33:44:55") is True
    assert is_locally_administered("B8:27:EB:00:00:00") is False


def test_shared_lookup_real_vendor():
    oui = shared_lookup()
    assert oui.size > 30000  # base IEEE real cargada
    assert "Raspberry Pi" in (oui.lookup("B8:27:EB:11:22:33") or "")
    assert "Cisco" in (oui.lookup("FC:FB:FB:00:00:00") or "")


def test_lookup_random_mac_message():
    oui = shared_lookup()
    # MAC localmente administrada no está en el registro -> mensaje de aleatoria
    assert "aleatoria" in (oui.lookup("FA:11:22:33:44:55") or "").lower()


def test_lookup_unknown_returns_none(tmp_path):
    # Con un CSV vacío, un OUI global desconocido devuelve None
    p = tmp_path / "oui.csv"
    p.write_text("oui,vendor\n", encoding="utf-8")
    empty = OUILookup(p).load()
    assert empty.lookup("B8:27:EB:00:00:00") is None
