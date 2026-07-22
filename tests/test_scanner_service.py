"""Tests del servicio de escaneo (reconciliacion), con la red mockeada."""
from datetime import datetime, timedelta, timezone

import agent.scanner_service as ss
from agent.discovery import DiscoveredDevice
from agent.scanner_service import ScannerService


def _dev(mac, ip, vendor="Cisco Systems, Inc", dtype="Red (Cisco)"):
    return DiscoveredDevice(mac=mac, ip=ip, iface="eth0", vendor=vendor,
                            hostname=None, device_type=dtype)


def _patch_scan(monkeypatch, devices):
    monkeypatch.setattr(ss, "list_active_subnets", lambda: [])
    monkeypatch.setattr(ss, "discover", lambda subnets=None, timeout=3.0: devices)


def test_new_device_creates_event_and_alert(db, monkeypatch):
    svc = ScannerService(db)
    _patch_scan(monkeypatch, [_dev("AA:BB:CC:00:00:01", "192.168.0.5")])
    summary = svc.scan_once()
    assert summary["online_count"] == 1
    assert len(summary["new"]) == 1
    assert svc.alerts.unack_count() == 1  # alerta new_device
    dev_id = summary["new"][0]["id"]
    evs = svc.events.list_for_device(dev_id)
    assert any(e["event_type"] == "connected" for e in evs)


def test_reconnect_and_disconnect(db, monkeypatch):
    svc = ScannerService(db)
    d = _dev("AA:BB:CC:00:00:01", "192.168.0.5")
    _patch_scan(monkeypatch, [d])
    svc.scan_once()                      # alta
    s2 = svc.scan_once()                 # sigue online -> sin reconnect
    assert s2["reconnected"] == [] and s2["new"] == []
    _patch_scan(monkeypatch, [])         # desaparece
    s3 = svc.scan_once()
    assert len(s3["disconnected"]) == 1
    _patch_scan(monkeypatch, [d])        # vuelve
    s4 = svc.scan_once()
    assert len(s4["reconnected"]) == 1 and s4["new"] == []


def test_ip_change_event(db, monkeypatch):
    svc = ScannerService(db)
    _patch_scan(monkeypatch, [_dev("AA:BB:CC:00:00:01", "192.168.0.5")])
    svc.scan_once()
    _patch_scan(monkeypatch, [_dev("AA:BB:CC:00:00:01", "192.168.0.9")])
    s = svc.scan_once()
    assert len(s["ip_changed"]) == 1
    assert s["ip_changed"][0]["from"] == "192.168.0.5"
    assert s["ip_changed"][0]["to"] == "192.168.0.9"


def test_scan_error_is_caught(db, monkeypatch):
    svc = ScannerService(db)
    monkeypatch.setattr(ss, "list_active_subnets", lambda: [])

    def boom(*a, **k):
        raise RuntimeError("fallo de red")
    monkeypatch.setattr(ss, "discover", boom)
    out = svc.scan_once()
    assert "error" in out  # no propaga la excepcion


def test_prune_now(db, monkeypatch):
    svc = ScannerService(db, retention_days=30)
    _patch_scan(monkeypatch, [_dev("AA:BB:CC:00:00:01", "192.168.0.5")])
    svc.scan_once()
    # inyecta un evento viejo
    dev = svc.devices.get_by_mac("AA:BB:CC:00:00:01")
    old = datetime.now(timezone.utc) - timedelta(days=60)
    svc.events.add(dev["id"], "disconnected", ts=old)
    res = svc.prune_now()
    assert res.get("events_pruned", 0) >= 1
