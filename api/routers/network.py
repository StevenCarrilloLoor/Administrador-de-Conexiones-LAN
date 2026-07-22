"""Endpoints de red: escaneo inmediato y test de velocidad."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..logging_setup import audit
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


@router.post("/speedtest")
async def speedtest(request: Request):
    """Mide latencia/descarga/subida contra Cloudflare (Fase 3).

    Es POST porque genera trafico de red real. La medicion (bloqueante) corre en
    un threadpool para no bloquear el event loop.
    """
    from agent.speedtest import run_speedtest
    result = await run_in_threadpool(run_speedtest)
    audit("speedtest", ok=result.get("ok"),
          download_mbps=result.get("download_mbps"),
          upload_mbps=result.get("upload_mbps"))
    if not result.get("ok"):
        raise HTTPException(status_code=502,
                            detail=result.get("error", "fallo el test de velocidad"))
    return result
