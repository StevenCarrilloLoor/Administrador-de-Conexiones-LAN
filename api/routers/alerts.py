"""Endpoints de alertas."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _to_out(row: dict) -> dict:
    out = dict(row)
    out["acknowledged"] = bool(row.get("acknowledged"))
    return out


@router.get("", response_model=list[AlertOut])
def list_alerts(request: Request, limit: int = 100, include_ack: bool = True):
    return [_to_out(r) for r in
            request.app.state.alert_repo.list_recent(limit=limit, include_ack=include_ack)]


@router.post("/{alert_id}/ack", status_code=204)
def ack_alert(alert_id: int, request: Request):
    if not request.app.state.alert_repo.acknowledge(alert_id):
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
