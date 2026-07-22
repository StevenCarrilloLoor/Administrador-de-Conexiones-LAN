"""Deteccion de requisitos de plataforma: privilegios de administrador y Npcap.

Regla de la especificacion (7.2): si falta Npcap o faltan privilegios de admin,
la app debe *detectarlo y explicarlo con claridad*, nunca fallar en silencio.
"""
from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path


def is_windows() -> bool:
    return os.name == "nt" or platform.system().lower().startswith("win")


def is_admin() -> bool:
    """True si el proceso corre elevado (admin en Windows, root en POSIX)."""
    if is_windows():
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        return False


def npcap_installed() -> bool:
    """Comprueba la presencia de Npcap en Windows.

    Busca la carpeta de instalacion y la DLL wpcap. En sistemas no-Windows el
    concepto no aplica (se usa libpcap del SO) y se devuelve True.
    """
    if not is_windows():
        return True
    candidates = [
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "Npcap",
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wpcap.dll",
        Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SysWOW64" / "Npcap",
        Path(r"C:\Program Files\Npcap"),
    ]
    return any(p.exists() for p in candidates)


def scapy_layer2_available() -> bool:
    """Verifica que scapy pueda abrir sockets de capa 2 (envio/recepcion ARP)."""
    try:
        from scapy.all import conf  # noqa: WPS433
        # En Windows scapy usa libpcap/Npcap; conf.use_pcap suele estar activo.
        return conf.L2socket is not None
    except Exception:
        return False


@dataclass
class Capabilities:
    platform: str
    is_admin: bool
    npcap: bool
    layer2: bool
    can_scan: bool
    messages: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "platform": self.platform,
            "is_admin": self.is_admin,
            "npcap_installed": self.npcap,
            "layer2_available": self.layer2,
            "can_scan": self.can_scan,
            "messages": self.messages,
        }


def check_capabilities() -> Capabilities:
    win = is_windows()
    admin = is_admin()
    npcap = npcap_installed()
    layer2 = scapy_layer2_available()
    messages: list[str] = []

    if win and not npcap:
        messages.append(
            "Npcap NO detectado. Instalalo desde https://npcap.com/#download "
            "(marca la opcion 'WinPcap API-compatible Mode'). Sin Npcap no se puede "
            "escanear ni controlar la red en Windows."
        )
    if not layer2 and (npcap or not win):
        messages.append(
            "scapy no pudo inicializar la captura de capa 2. Revisa Npcap/permisos."
        )

    # El escaneo ARP requiere Npcap (en Windows) + captura de capa 2. Los privilegios de
    # administrador NO son estrictamente necesarios para escanear cuando Npcap esta en modo
    # compatible (verificado en la practica), pero SI para el control activo (bloqueo/limite,
    # Fase 2). Por eso 'admin' es advertencia, no bloqueo del escaneo.
    can_scan = layer2 and (npcap or not win)

    if not admin:
        if win:
            messages.append(
                "Sin privilegios de administrador: el escaneo suele funcionar con Npcap, "
                "pero el control activo (bloqueo/limite de la Fase 2) SI requiere ejecutar "
                "como administrador (clic derecho -> 'Ejecutar como administrador')."
            )
        else:
            messages.append(
                "Sin privilegios de root: el escaneo ARP crudo puede fallar; el control "
                "activo requiere privilegios elevados (sudo)."
            )

    if can_scan:
        head = ("Requisitos presentes: listo para escanear y controlar."
                if admin else "Listo para escanear (Npcap presente).")
        messages.insert(0, head)

    return Capabilities(
        platform=platform.platform(),
        is_admin=admin,
        npcap=npcap,
        layer2=layer2,
        can_scan=can_scan,
        messages=messages,
    )
