"""Endpoints de reglas (persistencia en Fase 1; enforcement activo en Fase 2)."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, HTTPException, Request

from ..logging_setup import audit
from ..models import RuleIn, RuleOut

router = APIRouter(prefix="/api/rules", tags=["rules"])

_VALID = {"block", "bandwidth_limit", "schedule"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _to_out(row: dict) -> dict:
    out = dict(row)
    out["active"] = bool(row.get("active"))
    return out


@router.get("", response_model=list[RuleOut])
def list_rules(request: Request, active_only: bool = False):
    return [_to_out(r) for r in request.app.state.rule_repo.all(active_only=active_only)]


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, request: Request):
    st = request.app.state

    # --- validaciones de entrada (devuelven 4xx, no 500) [B5] ---
    if body.rule_type not in _VALID:
        raise HTTPException(status_code=422,
                            detail=f"rule_type invalido; use uno de {sorted(_VALID)}")
    if body.device_id is None and not body.device_group:
        raise HTTPException(status_code=422,
                            detail="Indica device_id o device_group para la regla.")
    if body.device_id is not None and not st.device_repo.get(body.device_id):
        raise HTTPException(status_code=404,
                            detail=f"El dispositivo device_id={body.device_id} no existe.")
    if body.rule_type == "bandwidth_limit" and (body.limit_kbps is None or body.limit_kbps <= 0):
        raise HTTPException(status_code=422,
                            detail="La regla 'bandwidth_limit' requiere limit_kbps > 0.")
    if body.rule_type == "schedule":
        if not body.schedule_start or not body.schedule_end:
            raise HTTPException(status_code=422,
                                detail="La regla 'schedule' requiere schedule_start y schedule_end.")
        for label, val in (("schedule_start", body.schedule_start),
                           ("schedule_end", body.schedule_end)):
            if not _HHMM.match(val):
                raise HTTPException(status_code=422,
                                    detail=f"{label} debe tener formato HH:MM (00:00-23:59).")

    try:
        rid = st.rule_repo.add(
            rule_type=body.rule_type, device_id=body.device_id,
            device_group=body.device_group, limit_kbps=body.limit_kbps,
            schedule_start=body.schedule_start, schedule_end=body.schedule_end,
            days_of_week=body.days_of_week, active=body.active,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=422, detail=f"No se pudo crear la regla: {exc}")

    audit("rule_create", rule_id=rid, rule_type=body.rule_type,
          device_id=body.device_id, group=body.device_group)
    return _to_out(st.rule_repo.get(rid))


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request):
    if not request.app.state.rule_repo.delete(rule_id):
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    audit("rule_delete", rule_id=rule_id)
