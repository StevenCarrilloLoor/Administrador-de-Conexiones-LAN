"""Test de velocidad de internet (Fase 3).

Mide latencia, descarga y subida usando los endpoints publicos de Cloudflare
(https://speed.cloudflare.com). Sin dependencias pesadas: solo `requests`.
"""
from __future__ import annotations

import time

_ENDPOINT = "https://speed.cloudflare.com"


def run_speedtest(download_bytes: int = 25_000_000,
                  upload_bytes: int = 5_000_000,
                  timeout: float = 30.0) -> dict:
    try:
        import requests
    except Exception as exc:  # pragma: no cover
        return {"ok": False, "error": f"falta 'requests': {exc}"}

    result: dict = {"ok": False}
    try:
        # Latencia: tiempo de una respuesta de 0 bytes
        t0 = time.time()
        requests.get(f"{_ENDPOINT}/__down?bytes=0", timeout=10)
        latency_ms = (time.time() - t0) * 1000.0

        # Descarga
        got = 0
        t0 = time.time()
        with requests.get(f"{_ENDPOINT}/__down?bytes={download_bytes}",
                          stream=True, timeout=timeout) as r:
            for chunk in r.iter_content(65536):
                got += len(chunk)
        down_dt = time.time() - t0
        down_mbps = (got * 8 / 1e6) / down_dt if down_dt > 0 else 0.0

        # Subida
        payload = b"0" * upload_bytes
        t0 = time.time()
        requests.post(f"{_ENDPOINT}/__up", data=payload, timeout=timeout)
        up_dt = time.time() - t0
        up_mbps = (len(payload) * 8 / 1e6) / up_dt if up_dt > 0 else 0.0

        result = {
            "ok": True,
            "latency_ms": round(latency_ms, 1),
            "download_mbps": round(down_mbps, 2),
            "upload_mbps": round(up_mbps, 2),
            "downloaded_bytes": got,
            "server": _ENDPOINT,
        }
    except Exception as exc:
        result = {"ok": False, "error": str(exc)}
    return result
