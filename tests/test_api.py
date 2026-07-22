"""Tests de la API (in-proceso, sin abrir puertos). Cubren los arreglos aplicados."""


async def test_status(client):
    r = await client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == 3
    assert body["oui_prefixes"] > 30000
    assert body["config"]["auth_enabled"] is False
    assert "capabilities" in body


async def test_no_cors_header(client):
    # B1: sin middleware CORS, no debe aparecer el header cross-origin
    r = await client.get("/api/status", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


async def test_devices_empty_then_seeded(client, app, seed):
    assert (await client.get("/api/devices")).json() == []
    seed(app, mac="AA:BB:CC:00:00:01", ip="192.168.0.5", vendor="Cisco Systems, Inc")
    r = await client.get("/api/devices")
    data = r.json()
    assert len(data) == 1
    assert data[0]["mac"] == "AA:BB:CC:00:00:01"
    assert data[0]["display_name"]  # derivado no vacio


async def test_device_detail_and_history(client, app, seed):
    res = seed(app, mac="AA:BB:CC:00:00:02", ip="192.168.0.6")
    app.state.event_repo.add(res.device_id, "connected", detail="IP 192.168.0.6")
    r = await client.get(f"/api/devices/{res.device_id}")
    assert r.status_code == 200
    assert len(r.json()["history"]) == 1


async def test_device_404(client):
    assert (await client.get("/api/devices/99999")).status_code == 404


async def test_patch_updates_and_length_validation(client, app, seed):
    res = seed(app, mac="AA:BB:CC:00:00:03", ip="192.168.0.7")
    ok = await client.patch(f"/api/devices/{res.device_id}",
                            json={"custom_name": "Notebook", "device_group": "familia"})
    assert ok.status_code == 200 and ok.json()["custom_name"] == "Notebook"
    # M7: nombre demasiado largo -> 422
    bad = await client.patch(f"/api/devices/{res.device_id}",
                             json={"custom_name": "x" * 200})
    assert bad.status_code == 422


async def test_rules_validation(client, app, seed):
    # falta device_id y device_group -> 422
    assert (await client.post("/api/rules", json={"rule_type": "block"})).status_code == 422
    # device_id inexistente -> 404 (B5, antes 500)
    r = await client.post("/api/rules", json={"rule_type": "block", "device_id": 99999})
    assert r.status_code == 404
    # bandwidth_limit sin kbps -> 422
    res = seed(app, mac="AA:BB:CC:00:00:04", ip="192.168.0.8")
    r = await client.post("/api/rules",
                          json={"rule_type": "bandwidth_limit", "device_id": res.device_id})
    assert r.status_code == 422
    # schedule con formato malo -> 422
    r = await client.post("/api/rules", json={"rule_type": "schedule",
                          "device_id": res.device_id, "schedule_start": "25:99",
                          "schedule_end": "07:00"})
    assert r.status_code == 422
    # schedule valido -> 201
    r = await client.post("/api/rules", json={"rule_type": "schedule",
                          "device_id": res.device_id, "schedule_start": "22:00",
                          "schedule_end": "07:00"})
    assert r.status_code == 201 and r.json()["rule_type"] == "schedule"


async def test_rule_delete_404(client):
    assert (await client.delete("/api/rules/99999")).status_code == 404


async def test_alerts_limit_validation(client):
    # M6: limite fuera de rango -> 422
    assert (await client.get("/api/alerts?limit=0")).status_code == 422
    assert (await client.get("/api/alerts?limit=-1")).status_code == 422
    assert (await client.get("/api/alerts?limit=10")).status_code == 200


async def test_scan_is_post_not_get(client, app):
    # B2: GET ya no dispara escaneo (404/405 por el montaje estatico catch-all);
    # lo importante es que NO sea 200. POST funciona (mock del escaneo).
    assert (await client.get("/api/network/scan")).status_code in (404, 405)
    app.state.scanner.scan_once = lambda: {
        "online_count": 2, "new": [], "reconnected": [], "disconnected": [],
        "ip_changed": [], "scanned_subnets": [], "timestamp": "2026-01-01T00:00:00+00:00",
    }
    r = await client.post("/api/network/scan")
    assert r.status_code == 200 and r.json()["online_count"] == 2


async def test_phase2_endpoints_501(client, app, seed):
    # El control activo (bloqueo/limite via ARP) sigue deshabilitado honestamente.
    res = seed(app, mac="AA:BB:CC:00:00:05", ip="192.168.0.9")
    assert (await client.post(f"/api/devices/{res.device_id}/block")).status_code == 501
    assert (await client.post(f"/api/devices/{res.device_id}/limit",
                              json={"kbps": 100})).status_code == 501


async def test_stats_vendors(client, app, seed):
    seed(app, mac="AA:BB:CC:00:00:06", ip="192.168.0.11", vendor="Cisco Systems, Inc")
    r = await client.get("/api/stats/vendors")
    assert r.status_code == 200 and isinstance(r.json(), list)


async def test_static_dashboard_served(client):
    assert (await client.get("/")).status_code == 200
    assert (await client.get("/styles.css")).status_code == 200
    assert (await client.get("/app.js")).status_code == 200
    # B6: Chart.js vendorizado se sirve localmente
    assert (await client.get("/vendor/chart.umd.min.js")).status_code == 200
