"""Defensa propia anti-ARP-spoofing (Fase 3) — PURAMENTE DEFENSIVA.

Monitorea la entrada ARP del gateway EN ESTE equipo. Si la MAC del gateway cambia
de forma inesperada (sintoma de que alguien intenta envenenar tu tabla ARP para
hacerte man-in-the-middle), lo detecta, alerta y —si se pide— fija la entrada ARP
local de forma estatica para protegerte.

No envia paquetes forjados ni ataca a nadie: solo lee/escribe la tabla ARP de tu
propia maquina (`arp -a` / `arp -s`) y observa la red.
"""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Optional

log = logging.getLogger("lanmanager.arp_defense")

_ARP_LINE = re.compile(r"(\d{1,3}(?:\.\d{1,3}){3})\s+([0-9A-Fa-f]{2}(?:[-:][0-9A-Fa-f]{2}){5})")


def read_arp_table() -> dict[str, str]:
    """Lee la tabla ARP local (`arp -a`). Devuelve {ip: MAC_normalizada}."""
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=10)
        table: dict[str, str] = {}
        for line in out.stdout.splitlines():
            m = _ARP_LINE.search(line)
            if m:
                ip = m.group(1)
                mac = m.group(2).replace("-", ":").upper()
                table[ip] = mac
        return table
    except Exception as exc:
        log.warning("No se pudo leer la tabla ARP: %s", exc)
        return {}


def gateway_mac(gateway_ip: str) -> Optional[str]:
    return read_arp_table().get(gateway_ip)


def pin_gateway(gateway_ip: str, mac: str) -> tuple[bool, str]:
    """Fija una entrada ARP estatica local para el gateway (requiere admin)."""
    try:
        mac_dash = mac.replace(":", "-").lower()
        subprocess.run(["arp", "-s", gateway_ip, mac_dash],
                       capture_output=True, text=True, timeout=10, check=True)
        return True, f"ARP fijada: {gateway_ip} -> {mac}"
    except Exception as exc:
        return False, str(exc)


class ArpDefense:
    """Vigila la MAC del gateway y detecta envenenamiento. Guarda la MAC de
    referencia en settings ('arp_baseline_<ip>')."""

    def __init__(self, settings, gateway_ip: Optional[str] = None):
        self.settings = settings
        self.gateway_ip = gateway_ip

    def _key(self, ip: str) -> str:
        return f"arp_baseline_{ip}"

    def set_baseline(self, gateway_ip: str, mac: Optional[str] = None) -> Optional[str]:
        mac = mac or gateway_mac(gateway_ip)
        if mac:
            self.settings.set(self._key(gateway_ip), mac)
        return mac

    def check(self, gateway_ip: str) -> dict:
        """Compara la MAC actual del gateway con la de referencia.

        Devuelve {gateway, baseline, current, spoofed}. Si no hay referencia, la
        establece con la MAC actual (primer arranque).
        """
        current = gateway_mac(gateway_ip)
        baseline = self.settings.get(self._key(gateway_ip))
        if not baseline:
            if current:
                self.settings.set(self._key(gateway_ip), current)
            return {"gateway": gateway_ip, "baseline": current, "current": current,
                    "spoofed": False, "first_run": True}
        spoofed = bool(current) and current != baseline
        return {"gateway": gateway_ip, "baseline": baseline, "current": current,
                "spoofed": spoofed, "first_run": False}
