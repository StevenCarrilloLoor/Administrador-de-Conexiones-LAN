"""Tests de inferencia heuristica de tipo de dispositivo."""
from agent.device_type import infer_device_type


def test_gateway_wins():
    assert infer_device_type("Cualquier fabricante", "algo", is_gateway=True) == "Router / Gateway"


def test_hostname_hint_priority():
    # el hostname manda sobre el vendor
    assert "iPhone" in infer_device_type("Intel", "iPhone-de-Juan")


def test_vendor_hint():
    assert "Raspberry" in infer_device_type("Raspberry Pi Foundation", None)
    assert "Camara" in infer_device_type("Hangzhou Hikvision Digital", None)
    assert "IoT" in infer_device_type("Tuya Smart Inc.", None)


def test_unknown_returns_none():
    assert infer_device_type("Fabricante Rarisimo SA", None) is None
    assert infer_device_type(None, None) is None
