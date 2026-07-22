"""Endpoints de reglas (persistencia en Fase 1; enforcement activo en Fase 2)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..logging_setup import audit
from ..models import RuleIn, RuleOut

router = APIRouter(prefix="/api/rules", tags=["rules"])

_VALID = {"block", "bandwidth_limit", "schedule"}


def _to_out(row: dict) -> dict:
    out = dict(row)
    out["active"] = bool(row.get("active"))
    return out


@router.get("", response_model=list[RuleOut])
def list_rules(request: Request, active_only: bool = False):
    return [_to_out(r) for r in request.app.state.rule_repo.all(active_only=active_only)]


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(body: RuleIn, request: Request):
    if body.rule_type not in _VALID:
        raise HTTPException(status_code=422,
                            detail=f"rule_type invalido; use uno de {sorted(_VALID)}")
    st = request.app.state
    rid = st.rule_repo.add(
        rule_type=body.rule_type, device_id=body.device_id,
        device_group=body.device_group, limit_kbps=body.limit_kbps,
        schedule_start=body.schedule_start, schedule_end=body.schedule_end,
        days_of_week=body.days_of_week, active=body.active,
    )
    audit("rule_create", rule_id=rid, rule_type=body.rule_type,
          device_id=body.device_id, group=body.device_group)
    row = next((r for r in st.rule_repo.all() if r["id"] == rid), None)
    return _to_out(row)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request):
    if not request.app.state.rule_repo.delete(rule_id):
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    audit("rule_delete", rule_id=rule_id)
