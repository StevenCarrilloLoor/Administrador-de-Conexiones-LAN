"""Enumeracion de interfaces de red activas y sus subredes IPv4.

Se apoya en la tabla de rutas de scapy (multiplataforma). Devuelve una subred por
interfaz FISICA con IP local, para escanear la LAN real (Fase 1).

Excluye adaptadores VIRTUALES o de VPN (Radmin, Hamachi, VMware, Hyper-V, TAP, etc.),
porque esas redes contienen equipos ajenos y hacen que el propio equipo aparezca
duplicado (una vez por adaptador). Ver `_VIRTUAL_PATTERNS`.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Optional

# Subcadenas (en minusculas) de descripciones de adaptadores a EXCLUIR del escaneo.
_VIRTUAL_PATTERNS = (
    "radmin", "hamachi", "zerotier", "tailscale", "wireguard", "openvpn",
    "nordlynx", "proton", "tap-windows", "tap adapter", "vpn",
    "virtual", "vmware", "virtualbox", "hyper-v", "vethernet",
    "loopback", "bluetooth", "wan miniport", "teredo", "isatap", "6to4",
    "pseudo-interface", "docker", "wi-fi direct", "vswitch",
)


@dataclass
class ActiveSubnet:
    iface: str            # nombre/ID de la interfaz
    local_ip: str         # IP de la PC en esa subred
    cidr: str             # subred a escanear, p. ej. 192.168.0.0/24
    gateway: Optional[str]  # gateway si se conoce
    host_count: int       # cantidad de hosts direccionables
    description: str = ""  # descripcion del adaptador (Windows)

    def as_dict(self) -> dict:
        return {
            "iface": str(self.iface),
            "local_ip": self.local_ip,
            "cidr": self.cidr,
            "gateway": self.gateway,
            "host_count": self.host_count,
            "description": self.description,
        }


def _iface_name(iface) -> str:
    for attr in ("name", "description"):
        val = getattr(iface, attr, None)
        if val:
            return str(val)
    return str(iface)


def is_virtual_description(desc: Optional[str]) -> bool:
    d = (desc or "").lower()
    return any(p in d for p in _VIRTUAL_PATTERNS)


def ip_to_description() -> dict[str, str]:
    """Mapa IP-local -> descripcion del adaptador (Windows). {} en otros SO o si falla."""
    out: dict[str, str] = {}
    try:
        from scapy.arch.windows import get_windows_if_list  # solo Windows
        for it in get_windows_if_list():
            desc = str(it.get("description") or it.get("name") or "")
            for ip in (it.get("ips") or []):
                out[str(ip)] = desc
    except Exception:
        pass
    return out


def list_active_subnets(max_prefixlen_hosts: int = 4096,
                        include_virtual: bool = False) -> list[ActiveSubnet]:
    """Devuelve subredes IPv4 locales candidatas a escanear (solo fisicas por defecto).

    Filtra loopback (127/8), link-local (169.254/16), rutas de host (/31,/32) y —salvo
    include_virtual=True— adaptadores virtuales/VPN (por descripcion).
    """
    from scapy.all import conf  # import diferido: solo cuando se usa

    descriptions = ip_to_description()
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

            # Excluir adaptadores virtuales / VPN por descripcion
            desc = descriptions.get(str(out_ip), "") or getattr(iface, "description", "") or ""
            if not include_virtual and is_virtual_description(desc):
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
                description=desc,
            )
            results[sub.cidr] = sub
        except Exception:
            continue

    return list(results.values())
