"""Inferencia heuristica del tipo de dispositivo.

IMPORTANTE: es una *suposicion* basada en el fabricante (OUI) y el hostname.
No es un dato autoritativo; la interfaz debe mostrarlo como inferencia. Nunca se
inventa: si no hay señal suficiente, se devuelve None (la UI muestra "Desconocido").
"""
from __future__ import annotations

from typing import Optional

# (subcadena_en_minusculas, etiqueta). Orden: primero lo mas especifico.
_VENDOR_HINTS: list[tuple[str, str]] = [
    ("raspberry pi", "SBC / Raspberry Pi"),
    ("espressif", "IoT (ESP8266/ESP32)"),
    ("tuya", "IoT (smart home)"),
    ("sonos", "Altavoz / Audio"),
    ("amazon", "IoT / Echo / Fire"),
    ("google", "IoT / Chromecast / Nest"),
    ("nest", "IoT / Nest"),
    ("ring", "Camara / Timbre"),
    ("hikvision", "Camara IP"),
    ("dahua", "Camara IP"),
    ("axis communications", "Camara IP"),
    ("roku", "TV / Streaming"),
    ("apple", "Apple (iPhone/Mac/iPad)"),
    ("samsung", "Samsung (movil/TV)"),
    ("lg electronics", "LG (TV/electrodomestico)"),
    ("xiaomi", "Xiaomi (movil/IoT)"),
    ("huawei", "Huawei (movil/red)"),
    ("oneplus", "Movil"),
    ("motorola mobility", "Movil"),
    ("sony", "Sony (consola/TV)"),
    ("nintendo", "Consola de juegos"),
    ("microsoft", "PC / Xbox / Surface"),
    ("intel", "PC / laptop (NIC)"),
    ("realtek", "PC / laptop (NIC)"),
    ("dell", "PC / laptop"),
    ("hewlett packard", "PC / impresora HP"),
    ("hp inc", "PC / impresora HP"),
    ("asustek", "PC / router ASUS"),
    ("giga-byte", "PC (Gigabyte)"),
    ("liteon", "PC / laptop"),
    ("azurewave", "PC / laptop (WiFi)"),
    ("brother", "Impresora"),
    ("canon", "Impresora / Camara"),
    ("epson", "Impresora"),
    ("tp-link", "Red (router/AP TP-Link)"),
    ("ubiquiti", "Red (Ubiquiti)"),
    ("mikrotik", "Red (MikroTik)"),
    ("cisco", "Red (Cisco)"),
    ("netgear", "Red (Netgear)"),
    ("d-link", "Red (D-Link)"),
    ("zte", "Red / Movil (ZTE)"),
    ("arris", "Router / Modem"),
    ("technicolor", "Router / Modem"),
    ("vmware", "Maquina virtual"),
    ("virtualbox", "Maquina virtual"),
    ("xensource", "Maquina virtual"),
    ("microsoft corporation", "PC / VM (Hyper-V)"),
]

_HOSTNAME_HINTS: list[tuple[str, str]] = [
    ("iphone", "Apple (iPhone)"),
    ("ipad", "Apple (iPad)"),
    ("macbook", "Apple (Mac)"),
    ("android", "Movil (Android)"),
    ("galaxy", "Samsung (movil)"),
    ("desktop-", "PC (Windows)"),
    ("laptop-", "PC (Windows)"),
    ("pc-", "PC"),
    ("printer", "Impresora"),
    ("epson", "Impresora"),
    ("chromecast", "TV / Streaming"),
    ("roku", "TV / Streaming"),
    ("tv", "TV / Streaming"),
    ("raspberrypi", "SBC / Raspberry Pi"),
    ("switch", "Consola / Red"),
    ("xbox", "Consola (Xbox)"),
    ("playstation", "Consola (PlayStation)"),
    ("ps5", "Consola (PlayStation)"),
    ("router", "Red (router)"),
    ("gateway", "Red (gateway)"),
    ("esp_", "IoT (ESP)"),
    ("shelly", "IoT (Shelly)"),
    ("tasmota", "IoT (Tasmota)"),
]


def infer_device_type(
    vendor: Optional[str],
    hostname: Optional[str] = None,
    is_gateway: bool = False,
) -> Optional[str]:
    if is_gateway:
        return "Router / Gateway"
    host = (hostname or "").lower()
    for needle, label in _HOSTNAME_HINTS:
        if needle in host:
            return label
    vend = (vendor or "").lower()
    for needle, label in _VENDOR_HINTS:
        if needle in vend:
            return label
    return None
