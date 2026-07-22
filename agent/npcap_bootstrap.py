"""Bootstrap de Npcap: descarga y lanzamiento del instalador OFICIAL.

Limite real respetado: la version gratuita de Npcap NO tiene instalador silencioso
(eso es exclusivo de la version paga Npcap OEM). Por eso NO se automatizan los 2-3
clics del instalador grafico oficial; se automatiza todo lo anterior (deteccion,
descarga) y lo posterior (espera y continuacion). No se usan workarounds no oficiales.

Fuente: proyecto Nmap / npcap.com (unica fuente confiable). La descarga es por HTTPS
desde el dominio oficial y el instalador es el ejecutable firmado por Insecure.Com LLC.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable, Optional

# Pagina de distribucion oficial y fallback verificado (npcap-1.88, 2026-05-06).
NPCAP_DIST_PAGE = "https://npcap.com/dist/"
FALLBACK_INSTALLER_URL = "https://npcap.com/dist/npcap-1.88.exe"

ProgressCb = Callable[[int, int], None]


def latest_installer_url(timeout: float = 15.0) -> str:
    """Devuelve la URL del instalador estable mas nuevo.

    Parsea el listado oficial y elige la mayor version npcap-X.YZ.exe. Si algo
    falla (sin red, formato cambiado), cae al fallback verificado.
    """
    try:
        req = urllib.request.Request(NPCAP_DIST_PAGE, headers={"User-Agent": "AdministradorLAN"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", "replace")
        matches = re.findall(r"npcap-(\d+)\.(\d+)\.exe", html)
        stable = [(int(a), int(b)) for a, b in matches]
        # excluir betas/debug ya filtrados por el patron; elegir el mayor
        if stable:
            major, minor = max(stable)
            return f"https://npcap.com/dist/npcap-{major}.{minor:02d}.exe"
    except Exception:
        pass
    return FALLBACK_INSTALLER_URL


def download_installer(dest_dir: str | Path, progress_cb: Optional[ProgressCb] = None,
                       timeout: float = 60.0) -> Path:
    """Descarga el instalador oficial a dest_dir y devuelve la ruta local."""
    url = latest_installer_url()
    fname = url.rsplit("/", 1)[-1] or "npcap-installer.exe"
    dest = Path(dest_dir) / fname
    req = urllib.request.Request(url, headers={"User-Agent": "AdministradorLAN"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0) or 0)
        got = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if progress_cb:
                    progress_cb(got, total)
    return dest


def verify_installer_signature(installer_path: str | Path, timeout: float = 30.0):
    """Verifica la firma Authenticode del instalador antes de ejecutarlo. [M3]

    Devuelve (ok, detalle). En Windows usa Get-AuthenticodeSignature y exige estado
    'Valid' y que el firmante sea del proyecto (Insecure.Com / Npcap / Nmap). Fuera de
    Windows la verificacion no aplica y se omite.
    """
    if os.name != "nt":
        return True, "verificacion de firma omitida (no es Windows)"
    ps = (
        "$ErrorActionPreference='Stop';"
        f"$s = Get-AuthenticodeSignature -LiteralPath '{installer_path}';"
        "Write-Output $s.Status;"
        "if ($s.SignerCertificate) { Write-Output $s.SignerCertificate.Subject }"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=timeout,
        )
        lines = [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
        status = lines[0] if lines else "Unknown"
        subject = " ".join(lines[1:]) if len(lines) > 1 else ""
        trusted = any(t in subject.lower() for t in ("insecure.com", "npcap", "nmap"))
        ok = (status.lower() == "valid") and trusted
        return ok, f"status={status}; firmante={subject or 'desconocido'}"
    except Exception as exc:
        return False, f"no se pudo verificar la firma: {exc}"


def launch_installer_and_wait(installer_path: str | Path,
                              wait_timeout: float = 900.0,
                              poll: float = 2.0,
                              grace_after_exit: float = 8.0) -> bool:
    """Lanza el instalador oficial y espera a que Npcap quede instalado.

    Rompe la espera apenas el proceso del instalador termina (completado o cancelado),
    evitando quedar bloqueado hasta wait_timeout si el usuario cancela. [B4]
    No automatiza el instalador: el usuario da los 2-3 clics de la ventana estandar.
    """
    from .platform_checks import npcap_installed

    proc = subprocess.Popen([str(installer_path)])
    waited = 0.0
    while waited < wait_timeout:
        if npcap_installed():
            return True
        if proc.poll() is not None:
            # El instalador se cerro; dar una gracia breve por si el servicio tarda
            # en registrarse, y luego decidir sin esperar el timeout completo.
            grace = 0.0
            while grace < grace_after_exit:
                if npcap_installed():
                    return True
                time.sleep(1.0)
                grace += 1.0
            return npcap_installed()
        time.sleep(poll)
        waited += poll
    return npcap_installed()
