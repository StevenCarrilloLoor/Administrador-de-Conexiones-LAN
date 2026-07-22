"""Tests de Wake-on-LAN (Fase 3): construccion del magic packet, sin red real."""
import pytest

from agent import wol


def test_magic_packet_sent(monkeypatch):
    sent = []

    class FakeSock:
        def setsockopt(self, *a):
            pass

        def sendto(self, data, addr):
            sent.append((data, addr))

        def close(self):
            pass

    monkeypatch.setattr(wol.socket, "socket", lambda *a, **k: FakeSock())
    wol.send_magic_packet("AA:BB:CC:DD:EE:FF")
    # Se envia a los puertos 9 y 7
    assert {addr[1] for _, addr in sent} == {9, 7}
    data = sent[0][0]
    # 6 bytes de 0xFF seguidos de 16 repeticiones de la MAC (6 bytes) = 102 bytes
    assert len(data) == 102
    assert data[:6] == b"\xff" * 6
    assert data[6:12] == bytes.fromhex("AABBCCDDEEFF")


def test_invalid_mac_raises():
    with pytest.raises(ValueError):
        wol.send_magic_packet("no-es-una-mac")


def test_wake_ok(monkeypatch):
    monkeypatch.setattr(wol, "send_magic_packet", lambda mac: None)
    res = wol.wake("AA:BB:CC:DD:EE:FF")
    assert res["ok"] is True
    assert res["mac"] == "AA:BB:CC:DD:EE:FF"


def test_wake_error(monkeypatch):
    def boom(mac):
        raise ValueError("MAC invalida")
    monkeypatch.setattr(wol, "send_magic_packet", boom)
    res = wol.wake("xx")
    assert res["ok"] is False and "MAC invalida" in res["error"]
