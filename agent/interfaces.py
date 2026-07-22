"""Enumeracion de interfaces de red activas y sus subredes IPv4.

Se apoya en la tabla de rutas de scapy (multiplataforma). Devuelve una subred
por interfaz con IP local, para escanear "todas las interfaces activas" (Fase 1).
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional


@dataclass
class ActiveSubnet:
    iface: str            # nombre/ID de la interfaz
    local_ip: str         # IP de la PC en esa subred
    cidr: str             # subred a escanear, p. ej. 192.168.0.0/24
    gateway: Optional[str]  # gateway si se conoce
    host_count: int       # cantidad de hosts direccionables

    def as_dict(self) -> dict:
        return {
            "iface": str(self.iface),
            "local_ip": self.local_ip,
            "cidr": self.cidr,
            "gateway": self.gateway,
            "host_count": self.host_count,
        }


def _iface_name(iface) -> str:
    for attr in ("name", "description"):
        val = getattr(iface, attr, None)
        if val:
            return str(val)
    return str(iface)


def list_active_subnets(max_prefixlen_hosts: int = 4096) -> list[ActiveSubnet]:
    """Devuelve subredes IPv4 locales candidatas a escanear.

    Filtra loopback (127/8) y link-local (169.254/16). Limita subredes enormes
    para no lanzar un escaneo de millones de IPs por accidente.
    """
    from scapy.all import conf  # import diferido: solo cuando se usa

    results: dict[str, ActiveSubnet] = {}
    gateways: dict[str, str] = {}

    # Primera pasada: detectar gateways por interfaz (destino 0.0.0.0)
    for net, msk, gw, iface, outip, metric in conf.route.routes:
        try:
            if net == 0 and msk == 0 and gw not in ("0.0.0.0", "::"):
                gateways[_iface_name(iface)] = gw
        except Exception:
            continue

    for net, msk, gw, iface, outip, metric in conf.route.routes:
        try:
            if msk == 0:
                continue  # ruta por defecto
            network_int = net & msk
            net_addr = ipaddress.IPv4Address(network_int)
            netmask = ipaddress.IPv4Address(msk)
            if net_addr.is_loopback or net_addr.is_link_local or net_addr.is_multicast:
                continue
            if outip in (None, "0.0.0.0"):
                continue
            out_ip = ipaddress.IPv4Address(outip)
            if out_ip.is_loopback or out_ip.is_link_local:
                continue
            network = ipaddress.IPv4Network(f"{net_addr}/{netmask}", strict=False)
            # Descartar rutas de host/broadcast (/31, /32): no son subredes LAN utiles.
            if network.prefixlen >= 31:
                continue
            if network.num_addresses > max_prefixlen_hosts:
                # Reducir a un /24 alrededor de la IP local para subredes gigantes
                network = ipaddress.IPv4Network(f"{outip}/24", strict=False)
            name = _iface_name(iface)
            sub = ActiveSubnet(
                iface=name,
                local_ip=str(out_ip),
                cidr=str(network),
                gateway=gateways.get(name),
                host_count=max(network.num_addresses - 2, 0),
            )
            results[sub.cidr] = sub
        except Exception:
            continue

    return list(results.values())
