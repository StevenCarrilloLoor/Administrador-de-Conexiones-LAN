"""Endpoints de dispositivos."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from db.repositories import parse_iso
from ..logging_setup import audit
from ..models import DeviceDetailOut, DeviceOut, DeviceUpdateIn

router = APIRouter(prefix="/api/devices", tags=["devices"])

_PHASE2_MSG = ("El control activo (bloqueo/limite via ARP) corresponde a la Fase 2 "
               "y aun no esta habilitado en esta entrega (Fase 1). El endpoint existe "
               "para completar el contrato de la API.")


def compute_online(last_seen: str | None, ttl_seconds: int) -> bool:
    dt = parse_iso(last_seen)
    if dt is None:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() <= ttl_seconds


def display_name(row: dict) -> str:
    return (row.get("custom_name") or row.get("hostname")
            or row.get("vendor") or row.get("mac") or "?")


def to_device_out(row: dict, ttl: int) -> dict:
    out = dict(row)
    out["is_random_mac"] = bool(row.get("is_random_mac"))
    out["is_blocked"] = bool(row.get("is_blocked"))
    out["online"] = compute_online(row.get("last_seen"), ttl)
    out["display_name"] = display_name(row)
    return out


@router.get("", response_model=list[DeviceOut])
def list_devices(request: Request):
    st = request.app.state
    ttl = st.config.online_ttl
    return [to_device_out(r, ttl) for r in st.device_repo.all()]


@router.get("/{device_id}", response_model=DeviceDetailOut)
def get_device(device_id: int, request: Request):
    st = request.app.state
    row = st.device_repo.get(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    out = to_device_out(row, st.config.online_ttl)
    out["history"] = st.event_repo.list_for_device(device_id, limit=200)
    return out


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, body: DeviceUpdateIn, request: Request):
    st = request.app.state
    if not st.device_repo.get(device_id):
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    row = st.device_repo.update_meta(
        device_id, custom_name=body.custom_name, device_group=body.device_group
    )
    audit("device_update", device_id=device_id,
          custom_name=body.custom_name, group=body.device_group)
    return to_device_out(row, st.config.online_ttl)


# --- Control activo: Fase 2 (endpoints presentes, deshabilitados honestamente) ---
@router.post("/{device_id}/block", status_code=501)
def block_device(device_id: int, request: Request):
    audit("block_requested", device_id=device_id, result="not_implemented_phase1")
    raise HTTPException(status_code=501, detail=_PHASE2_MSG)


@router.post("/{device_id}/unblock", status_code=501)
def unblock_device(device_id: int, request: Request):
    audit("unblock_requested", device_id=device_id, result="not_implemented_phase1")
    raise HTTPException(status_code=501, detail=_PHASE2_MSG)


@router.post("/{device_id}/limit", status_code=501)
def limit_device(device_id: int, request: Request):
    audit("limit_requested", device_id=device_id, result="not_implemented_phase1")
    raise HTTPException(status_code=501, detail=_PHASE2_MSG)


@router.delete("/{device_id}/limit", status_code=501)
def remove_limit(device_id: int, request: Request):
    audit("limit_remove_requested", device_id=device_id, result="not_implemented_phase1")
    raise HTTPException(status_code=501, detail=_PHASE2_MSG)
