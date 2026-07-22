"""Tests del filtrado de adaptadores virtuales/VPN en la enumeracion de subredes."""
import ipaddress
import sys
import types

import agent.interfaces as intf
from agent.interfaces import is_virtual_description, list_active_subnets


def test_is_virtual_description():
    assert is_virtual_description("Radmin VPN Ethernet Adapter") is True
    assert is_virtual_description("VMware Virtual Ethernet Adapter") is True
    assert is_virtual_description("Hyper-V Virtual Ethernet Adapter") is True
    assert is_virtual_description("VirtualBox Host-Only Ethernet Adapter") is True
    assert is_virtual_description("Intel(R) Wi-Fi 6 AX201 160MHz") is False
    assert is_virtual_description("Realtek Gaming GbE Family Controller") is False
    assert is_virtual_description(None) is False


def _ip_int(s):
    return int(ipaddress.IPv4Address(s))


def test_list_active_subnets_excludes_vpn(monkeypatch):
    # Tabla de rutas simulada: LAN real (192.168.100.x) + Radmin VPN (26.227.22.x)
    routes = [
        (0, 0, "192.168.100.1", "eth_real", "192.168.100.50", 10),
        (0, 0, "26.0.0.1", "radmin", "26.227.22.43", 20),
        (_ip_int("192.168.100.0"), _ip_int("255.255.255.0"), "0.0.0.0", "eth_real", "192.168.100.50", 10),
        (_ip_int("26.227.22.0"), _ip_int("255.255.255.0"), "0.0.0.0", "radmin", "26.227.22.43", 20),
    ]

    class FakeConf:
        class route:
            pass
    FakeConf.route.routes = routes
    fake_scapy_all = types.SimpleNamespace(conf=FakeConf)
    monkeypatch.setitem(sys.modules, "scapy.all", fake_scapy_all)
    monkeypatch.setattr(intf, "ip_to_description", lambda: {
        "192.168.100.50": "Intel(R) Wi-Fi 6 AX201",
        "26.227.22.43": "Radmin VPN Ethernet Adapter",
    })

    subs = list_active_subnets()
    cidrs = [s.cidr for s in subs]
    assert "192.168.100.0/24" in cidrs           # LAN real incluida
    assert not any(c.startswith("26.") for c in cidrs)  # VPN excluida


def test_include_virtual_keeps_all(monkeypatch):
    routes = [
        (_ip_int("26.227.22.0"), _ip_int("255.255.255.0"), "0.0.0.0", "radmin", "26.227.22.43", 20),
    ]

    class FakeConf:
        class route:
            pass
    FakeConf.route.routes = routes
    monkeypatch.setitem(sys.modules, "scapy.all", types.SimpleNamespace(conf=FakeConf))
    monkeypatch.setattr(intf, "ip_to_description", lambda: {
        "26.227.22.43": "Radmin VPN Ethernet Adapter"})
    subs = list_active_subnets(include_virtual=True)
    assert any(s.cidr.startswith("26.") for s in subs)  # con include_virtual, se conserva
