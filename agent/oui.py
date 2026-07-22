"""Resolucion de fabricante por OUI (los primeros 24 bits de la MAC).

Usa una base de datos IEEE MA-L real, incluida en `data/oui.csv` y consultada
100% sin conexion. El CSV se genera a partir del registro oficial de la IEEE
(mismo dato que distribuye la libreria `netaddr`). No hay mapeos inventados.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

_OUI_CSV = Path(__file__).resolve().parents[1] / "data" / "oui.csv"

_HEX_RE = re.compile(r"[0-9A-Fa-f]")


def normalize_mac(mac: str) -> str:
    """Normaliza a formato AA:BB:CC:DD:EE:FF en mayusculas."""
    hexchars = "".join(_HEX_RE.findall(mac or "")).upper()
    if len(hexchars) < 12:
        return (mac or "").upper()
    hexchars = hexchars[:12]
    return ":".join(hexchars[i:i + 2] for i in range(0, 12, 2))


def oui_prefix(mac: str) -> str:
    hexchars = "".join(_HEX_RE.findall(mac or "")).upper()
    return hexchars[:6]


def is_locally_administered(mac: str) -> bool:
    """True si el bit 'localmente administrado' (U/L) esta activo.

    Las MAC aleatorias de privacidad de moviles modernos tienen este bit en 1
    y NO figuran en el registro IEEE, por eso el vendor no resolvera.
    """
    hexchars = "".join(_HEX_RE.findall(mac or "")).upper()
    if len(hexchars) < 2:
        return False
    try:
        first_octet = int(hexchars[0:2], 16)
    except ValueError:
        return False
    return bool(first_octet & 0b00000010)


class OUILookup:
    """Carga perezosa del CSV a un diccionario prefijo->fabricante."""

    def __init__(self, csv_path: Path = _OUI_CSV):
        self.csv_path = csv_path
        self._table: dict[str, str] = {}
        self._loaded = False

    def load(self) -> "OUILookup":
        if self._loaded:
            return self
        table: dict[str, str] = {}
        if self.csv_path.exists():
            with open(self.csv_path, encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                for row in reader:
                    if len(row) >= 2 and row[0]:
                        table[row[0].strip().upper()] = row[1].strip()
        self._table = table
        self._loaded = True
        return self

    @property
    def size(self) -> int:
        return len(self._table)

    def lookup(self, mac: str) -> Optional[str]:
        if not self._loaded:
            self.load()
        prefix = oui_prefix(mac)
        vendor = self._table.get(prefix)
        if vendor:
            return vendor
        if is_locally_administered(mac):
            return "MAC aleatoria / localmente administrada"
        return None


# Instancia compartida (singleton perezoso)
_shared: Optional[OUILookup] = None


def shared_lookup() -> OUILookup:
    global _shared
    if _shared is None:
        _shared = OUILookup().load()
    return _shared
