"""Tests de las utilidades de Fase 3 via la API (in-proceso):
exportacion, Wake-on-LAN, notificaciones, defensa, vigilancia y test de velocidad."""
import agent.arp_defense as ad
import agent.interfaces as ifaces


# --------------------------------------------------------------------------- #
# Exportacion CSV / JSON
# --------------------------------------------------------------------------- #
async def test_export_devices_json(client, app, seed):
    seed(app, mac="AA:BB:CC:00:00:10", ip="192.168.0.10", hostname="pc")
    r = await client.get("/api/export/devices.json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "attachment" in r.headers["content-disposition"]
    data = r.json()
    assert any(d["mac"] == "AA:BB:CC:00:00:10" for d in data)


async def test_export_devices_csv(client, app, seed):
    seed(app, mac="AA:BB:CC:00:00:11", ip="192.168.0.11")
    r = await client.get("/api/export/devices.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "mac" in body.splitlines()[0]  # cabecera
    assert "AA:BB:CC:00:00:11" in body


async def test_export_events(client, app, seed):
    res = seed(app, mac="AA:BB:CC:00:00:12", ip="192.168.0.12")
    app.state.event_repo.add(res.device_id, "connected", detail="IP 192.168.0.12")
    rj = await client.get("/api/export/events.json")
    rc = await client.get("/api/export/events.csv")
    assert rj.status_code == 200 and rc.status_code == 200
    assert len(rj.json()) >= 1


# --------------------------------------------------------------------------- #
# Wake-on-LAN
# --------------------------------------------------------------------------- #
async def test_wake_device(client, app, seed, monkeypatch):
    res = seed(app, mac="AA:BB:CC:00:00:13", ip="192.168.0.13")
    import agent.wol as wolmod
    monkeypatch.setattr(wolmod, "wake", lambda mac: {"ok": True, "mac": mac})
    r = await client.post(f"/api/devices/{res.device_id}/wake")
    assert r.status_code == 200 and r.json()["ok"] is True


async def test_wake_device_404(client):
    assert (await client.post("/api/devices/99999/wake")).status_code == 404


# --------------------------------------------------------------------------- #
# Vigilancia (watch) + alerta de caida
# --------------------------------------------------------------------------- #
async def test_watch_toggle(client, app, seed):
    res = seed(app, mac="AA:BB:CC:00:00:14", ip="192.168.0.14")
    r = await client.post(f"/api/devices/{res.device_id}/watch", json={"watched": True})
    assert r.status_code == 200 and r.json()["is_watched"] is True
    r2 = await client.post(f"/api/devices/{res.device_id}/watch", json={"watched": False})
    assert r2.json()["is_watched"] is False


async def test_watch_404(client):
    assert (await client.post("/api/devices/99999/watch",
                              json={"watched": True})).status_code == 404


# --------------------------------------------------------------------------- #
# Notificaciones
# --------------------------------------------------------------------------- #
async def test_notifications_config_roundtrip(client):
    # por defecto, deshabilitadas
    r = await client.get("/api/notifications")
    assert r.status_code == 200 and r.json()["enabled"] is False
    # habilitar ntfy
    put = await client.put("/api/notifications", json={
        "ntfy_enabled": True, "ntfy_topic": "mi-red-privada"})
    assert put.status_code == 200 and put.json()["enabled"] is True
    # el topic se refleja en la config publica
    cfg = (await client.get("/api/notifications")).json()["config"]
    assert cfg["ntfy"]["topic"] == "mi-red-privada"


async def test_notifications_test_requires_backend(client):
    # sin backends habilitados -> 400
    assert (await client.post("/api/notifications/test")).status_code == 400


async def test_notifications_test_ok(client, monkeypatch):
    await client.put("/api/notifications", json={"ntfy_enabled": True, "ntfy_topic": "t"})
    from agent.notifier import NtfyNotifier
    monkeypatch.setattr(NtfyNotifier, "send", lambda self, t, m: (True, "HTTP 200"))
    r = await client.post("/api/notifications/test")
    assert r.status_code == 200
    assert r.json()["results"][0]["ok"] is True


async def test_notifications_secret_not_exposed(client):
    await client.put("/api/notifications", json={
        "telegram_enabled": True, "telegram_token": "SECRETO123",
        "telegram_chat_id": "999"})
    cfg = (await client.get("/api/notifications")).json()
    assert "SECRETO123" not in str(cfg)


# --------------------------------------------------------------------------- #
# Defensa anti-spoofing
# --------------------------------------------------------------------------- #
class _FakeSubnet:
    def __init__(self, gateway):
        self.gateway = gateway

    def as_dict(self):
        return {"gateway": self.gateway}


async def test_defense_status_no_gateway(client, monkeypatch):
    monkeypatch.setattr(ifaces, "list_active_subnets", lambda include_virtual=False: [])
    r = await client.get("/api/defense")
    assert r.status_code == 200 and r.json()["gateway"] is None


async def test_defense_status_with_gateway(client, monkeypatch):
    monkeypatch.setattr(ifaces, "list_active_subnets",
                        lambda include_virtual=False: [_FakeSubnet("192.168.1.1")])
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    r = await client.get("/api/defense")
    body = r.json()
    assert r.status_code == 200
    assert body["gateway"] == "192.168.1.1"
    assert body["spoofed"] is False


async def test_defense_baseline(client, monkeypatch):
    monkeypatch.setattr(ifaces, "list_active_subnets",
                        lambda include_virtual=False: [_FakeSubnet("192.168.1.1")])
    monkeypatch.setattr(ad, "gateway_mac", lambda ip: "AA:BB:CC:DD:EE:FF")
    r = await client.post("/api/defense/baseline")
    assert r.status_code == 200
    assert r.json()["baseline"] == "AA:BB:CC:DD:EE:FF"


# --------------------------------------------------------------------------- #
# Test de velocidad (Fase 3, ahora implementado)
# --------------------------------------------------------------------------- #
async def test_speedtest_ok(client, monkeypatch):
    import agent.speedtest as st
    monkeypatch.setattr(st, "run_speedtest",
                        lambda: {"ok": True, "latency_ms": 12.3,
                                 "download_mbps": 100.0, "upload_mbps": 20.0})
    r = await client.post("/api/network/speedtest")
    assert r.status_code == 200 and r.json()["download_mbps"] == 100.0


async def test_speedtest_failure(client, monkeypatch):
    import agent.speedtest as st
    monkeypatch.setattr(st, "run_speedtest", lambda: {"ok": False, "error": "sin internet"})
    r = await client.post("/api/network/speedtest")
    assert r.status_code == 502
