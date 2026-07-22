"""Tests de la defensa anti-spoofing (Fase 3). Puramente defensiva: se mockea
la lectura de la tabla ARP; no se envian paquetes ni se ataca a nadie."""
import agent.arp_defense as ad
from agent.arp_defense import ArpDefense
from db.repositories import SettingsRepository


def test_read_arp_table_parses_lines(monkeypatch):
    salida = (
        "Interfaz: 192.168.1.10 --- 0x5\n"
        "  Direccion de Internet   Direccion fisica      Tipo\n"
        "  192.168.1.1           aa-bb-cc-dd-ee-ff     dinamico\n"
        "  192.168.1.20          11-22-33-44-55-66     dinamico\n"
    )

    class R:
        stdout = salida
    monkeypatch.setattr(ad.subprocess, "run", lambda *a, **k: R())
    table = ad.read_arp_table()
    assert table["192.168.1.1"] == "AA:BB:CC:DD:EE:FF"
    assert table["192.168.1.20"] == "11:22:33:44:55:66"


def test_baseline_first_run_sets_reference(db, monkeypatch):
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    d = ArpDefense(SettingsRepository(db))
    res = d.check("192.168.1.1")
    assert res["first_run"] is True
    assert res["spoofed"] is False
    assert res["baseline"] == "AA:BB:CC:DD:EE:FF"


def test_spoof_detected_when_mac_changes(db, monkeypatch):
    s = SettingsRepository(db)
    d = ArpDefense(s)
    # primer arranque fija la referencia
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    d.check("192.168.1.1")
    # ahora la MAC del gateway "cambia" (posible envenenamiento)
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "66:66:66:66:66:66")
    res = d.check("192.168.1.1")
    assert res["spoofed"] is True
    assert res["baseline"] == "AA:BB:CC:DD:EE:FF"
    assert res["current"] == "66:66:66:66:66:66"


def test_no_spoof_when_mac_stable(db, monkeypatch):
    d = ArpDefense(SettingsRepository(db))
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    d.check("192.168.1.1")
    res = d.check("192.168.1.1")
    assert res["spoofed"] is False and res["first_run"] is False


def test_set_baseline_updates_reference(db, monkeypatch):
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    d = ArpDefense(SettingsRepository(db))
    mac = d.set_baseline("192.168.1.1")
    assert mac == "AA:BB:CC:DD:EE:FF"
    assert d.settings.get("arp_baseline_192.168.1.1") == "AA:BB:CC:DD:EE:FF"
