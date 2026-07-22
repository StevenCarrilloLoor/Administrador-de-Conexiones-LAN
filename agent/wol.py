"""Wake-on-LAN (Fase 3): enciende un equipo enviando el 'magic packet'."""
from __future__ import annotations

import socket

from .oui import normalize_mac


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    """Envia el magic packet WoL a la MAC dada (6x FF + 16x la MAC)."""
    hexmac = "".join(c for c in mac if c in "0123456789abcdefABCDEF")
    if len(hexmac) != 12:
        raise ValueError(f"MAC invalida: {mac}")
    packet = bytes.fromhex("FF" * 6 + hexmac * 16)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
        # tambien al puerto 7 (algunos equipos escuchan ahi)
        sock.sendto(packet, (broadcast, 7))
    finally:
        sock.close()


def wake(mac: str) -> dict:
    try:
        send_magic_packet(mac)
        return {"ok": True, "mac": normalize_mac(mac)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
