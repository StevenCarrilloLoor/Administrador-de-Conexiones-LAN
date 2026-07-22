"""Endpoints de red: escaneo inmediato y test de velocidad."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import ScanResult

router = APIRouter(prefix="/api/network", tags=["network"])


@router.post("/scan", response_model=ScanResult)
def force_scan(request: Request):
    """Fuerza un escaneo inmediato y devuelve el resumen.

    Es POST (no GET) porque tiene efectos secundarios: escribe dispositivos,
    eventos y alertas en la BD. [B2]
    """
    return request.app.state.scanner.scan_once()


@router.get("/subnets")
def subnets(request: Request):
    """Subredes activas detectadas (diagnostico, solo lectura)."""
    from agent.interfaces import list_active_subnets
    try:
        return [s.as_dict() for s in list_active_subnets()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/speedtest", status_code=501)
def speedtest(request: Request):
    """Test de velocidad: corresponde a la Fase 3."""
    raise HTTPException(
        status_code=501,
        detail="El test de velocidad de internet corresponde a la Fase 3.",
    )
