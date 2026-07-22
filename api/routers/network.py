"""Endpoints de red: escaneo inmediato y test de velocidad."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/scan")
def force_scan(request: Request):
    """Fuerza un escaneo inmediato y devuelve el resumen."""
    st = request.app.state
    result = st.scanner.scan_once()
    return result


@router.get("/subnets")
def subnets(request: Request):
    """Subredes activas detectadas (diagnostico)."""
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
