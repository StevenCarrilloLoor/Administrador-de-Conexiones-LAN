"""Endpoints de utilidades y seguridad (Fase 3):
exportacion CSV/JSON, Wake-on-LAN, notificaciones y defensa anti-spoofing."""
from __future__ import annotations

import csv
import io
import json as _json
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from ..logging_setup import audit

router = APIRouter(tags=["tools"])


# --------------------------------------------------------------------------- #
# Exportacion CSV / JSON
# --------------------------------------------------------------------------- #
def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _attachment(content: str, filename: str, media: str) -> Response:
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/export/devices.json")
def export_devices_json(request: Request):
    data = request.app.state.device_repo.all()
    return _attachment(_json.dumps(data, ensure_ascii=False, indent=2),
                       "dispositivos.json", "application/json")


@router.get("/api/export/devices.csv")
def export_devices_csv(request: Request):
    rows = request.app.state.device_repo.all()
    fields = ["id", "mac", "ip", "hostname", "vendor", "device_type", "custom_name",
              "device_group", "is_random_mac", "first_seen", "last_seen",
              "is_blocked", "bandwidth_limit_kbps"]
    return _attachment(_csv(rows, fields), "dispositivos.csv", "text/csv")


@router.get("/api/export/events.json")
def export_events_json(request: Request, limit: int = 5000):
    data = request.app.state.event_repo.recent(limit=limit)
    return _attachment(_json.dumps(data, ensure_ascii=False, indent=2),
                       "eventos.json", "application/json")


@router.get("/api/export/events.csv")
def export_events_csv(request: Request, limit: int = 5000):
    rows = request.app.state.event_repo.recent(limit=limit)
    fields = ["id", "device_id", "event_type", "detail", "timestamp"]
    return _attachment(_csv(rows, fields), "eventos.csv", "text/csv")


# --------------------------------------------------------------------------- #
# Wake-on-LAN
# --------------------------------------------------------------------------- #
@router.post("/api/devices/{device_id}/wake")
def wake_device(device_id: int, request: Request):
    dev = request.app.state.device_repo.get(device_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    from agent.wol import wake
    result = wake(dev["mac"])
    audit("wake_on_lan", device_id=device_id, mac=dev["mac"], ok=result.get("ok"))
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "fallo WoL"))
    return result


# --------------------------------------------------------------------------- #
# Notificaciones
# --------------------------------------------------------------------------- #
class NotifConfig(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    ntfy_enabled: Optional[bool] = None
    ntfy_server: Optional[str] = None
    ntfy_topic: Optional[str] = None
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[str] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_to: Optional[str] = None
    smtp_tls: Optional[bool] = None


@router.get("/api/notifications")
def get_notifications(request: Request):
    nm = request.app.state.notifier
    return {"enabled": nm.enabled, "config": nm.public_config()}


@router.put("/api/notifications")
def set_notifications(body: NotifConfig, request: Request):
    settings = request.app.state.settings_repo
    for key, value in body.model_dump(exclude_none=True).items():
        settings.set(f"notif_{key}", "true" if value is True else
                     ("false" if value is False else str(value)))
    audit("notifications_config_updated")
    nm = request.app.state.notifier
    return {"enabled": nm.enabled, "config": nm.public_config()}


@router.post("/api/notifications/test")
def test_notifications(request: Request):
    nm = request.app.state.notifier
    if not nm.enabled:
        raise HTTPException(status_code=400, detail="No hay backends de notificacion habilitados.")
    results = nm.notify("Administrador de Conexiones LAN",
                        "Notificacion de prueba: la configuracion funciona.")
    return {"results": results}


# --------------------------------------------------------------------------- #
# Defensa anti-spoofing (propio equipo)
# --------------------------------------------------------------------------- #
def _primary_gateway() -> Optional[str]:
    try:
        from agent.interfaces import list_active_subnets
        for s in list_active_subnets():
            if s.gateway:
                return s.gateway
    except Exception:
        pass
    return None


@router.get("/api/defense")
def defense_status(request: Request):
    gw = _primary_gateway()
    if not gw:
        return {"gateway": None, "spoofed": False, "detail": "No se detecto gateway."}
    return request.app.state.defense.check(gw)


@router.post("/api/defense/baseline")
def defense_reset_baseline(request: Request):
    gw = _primary_gateway()
    if not gw:
        raise HTTPException(status_code=400, detail="No se detecto gateway.")
    mac = request.app.state.defense.set_baseline(gw)
    audit("defense_baseline_set", gateway=gw, mac=mac)
    return {"gateway": gw, "baseline": mac}


@router.post("/api/defense/pin")
def defense_pin(request: Request):
    gw = _primary_gateway()
    if not gw:
        raise HTTPException(status_code=400, detail="No se detecto gateway.")
    from agent.arp_defense import gateway_mac, pin_gateway
    mac = gateway_mac(gw)
    if not mac:
        raise HTTPException(status_code=400, detail="No se pudo leer la MAC del gateway.")
    ok, detail = pin_gateway(gw, mac)
    audit("defense_pin", gateway=gw, mac=mac, ok=ok)
    if not ok:
        raise HTTPException(status_code=500, detail=f"No se pudo fijar la ARP (¿admin?): {detail}")
    return {"gateway": gw, "mac": mac, "detail": detail}
