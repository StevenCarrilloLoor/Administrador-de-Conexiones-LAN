"""Motor de descubrimiento: escaneo ARP de la LAN + enriquecimiento.

Devuelve dispositivos observados en el segmento local. El enriquecimiento
(fabricante, hostname, tipo) se hace sobre datos reales:
  * MAC/IP    -> respuesta ARP real del dispositivo
  * vendor    -> base OUI IEEE (offline)
  * hostname  -> DNS inverso real (con timeout)
  * tipo      -> heuristica etiquetada como inferencia
"""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .device_type import infer_device_type
from .interfaces import ActiveSubnet, list_active_subnets
from .oui import is_locally_administered, normalize_mac, shared_lookup


@dataclass
class DiscoveredDevice:
    mac: str
    ip: str
    iface: str
    vendor: Optional[str] = None
    hostname: Optional[str] = None
    device_type: Optional[str] = None
    is_gateway: bool = False
    is_self: bool = False
    is_random_mac: bool = False
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict:
        d = {
            "mac": self.mac, "ip": self.ip, "iface": self.iface,
            "vendor": self.vendor, "hostname": self.hostname,
            "device_type": self.device_type, "is_gateway": self.is_gateway,
            "is_self": self.is_self, "is_random_mac": self.is_random_mac,
        }
        return d


def resolve_hostname(ip: str, timeout: float = 0.6) -> Optional[str]:
    """DNS inverso con timeout. Devuelve None si no resuelve."""
    prev = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(prev)


def arp_scan_subnet(cidr: str, iface: Optional[str] = None,
                    timeout: float = 3.0, retry: int = 1) -> list[dict]:
    """Escaneo ARP de una subred. Devuelve [{ip, mac}]. Requiere Npcap/root."""
    from scapy.all import ARP, Ether, srp  # import diferido

    ether = Ether(dst="ff:ff:ff:ff:ff:ff")
    arp = ARP(pdst=cidr)
    kwargs = dict(timeout=timeout, retry=retry, verbose=False)
    if iface:
        kwargs["iface"] = iface
    answered, _ = srp(ether / arp, **kwargs)
    found = []
    for _, received in answered:
        found.append({"ip": received.psrc, "mac": normalize_mac(received.hwsrc)})
    return found


def _local_macs() -> set[str]:
    """MACs de las propias interfaces, para marcar el equipo que corre el agente."""
    macs: set[str] = set()
    try:
        from scapy.all import get_if_list, get_if_hwaddr
        for name in get_if_list():
            try:
                macs.add(normalize_mac(get_if_hwaddr(name)))
            except Exception:
                continue
    except Exception:
        pass
    return {m for m in macs if m and m != "00:00:00:00:00:00"}


def discover(
    subnets: Optional[list[ActiveSubnet]] = None,
    resolve_hostnames: bool = True,
    timeout: float = 3.0,
) -> list[DiscoveredDevice]:
    """Descubre dispositivos en todas las subredes activas y los enriquece."""
    if subnets is None:
        subnets = list_active_subnets()

    oui = shared_lookup()
    self_macs = _local_macs()

    # Escaneo ARP por subred, deduplicando por MAC (una MAC puede verse en varias)
    by_mac: dict[str, DiscoveredDevice] = {}
    gateways = {s.gateway for s in subnets if s.gateway}

    for sub in subnets:
        try:
            entries = arp_scan_subnet(sub.cidr, iface=sub.iface, timeout=timeout)
        except Exception:
            entries = []
        for e in entries:
            mac, ip = e["mac"], e["ip"]
            if not mac:
                continue
            if mac in by_mac:
                continue
            dev = DiscoveredDevice(
                mac=mac, ip=ip, iface=sub.iface,
                is_gateway=(ip in gateways),
                is_self=(mac in self_macs),
                is_random_mac=is_locally_administered(mac),
            )
            dev.vendor = oui.lookup(mac)
            by_mac[mac] = dev

        # Asegurar que el propio equipo aparezca aunque no responda a su ARP
        if sub.local_ip and sub.gateway:
            pass  # el host local suele responder; ver _local_macs para marcarlo

    devices = list(by_mac.values())

    # Resolucion de hostname en paralelo (I/O bound)
    if resolve_hostnames and devices:
        with ThreadPoolExecutor(max_workers=min(32, len(devices))) as pool:
            names = list(pool.map(lambda d: resolve_hostname(d.ip), devices))
        for dev, name in zip(devices, names):
            dev.hostname = name

    # Inferencia de tipo (etiquetada como suposicion)
    for dev in devices:
        dev.device_type = infer_device_type(dev.vendor, dev.hostname, dev.is_gateway)

    # Orden estable: gateway primero, luego por IP
    def sort_key(d: DiscoveredDevice):
        try:
            octets = tuple(int(x) for x in d.ip.split("."))
        except Exception:
            octets = (999,)
        return (not d.is_gateway, octets)

    devices.sort(key=sort_key)
    return devices
