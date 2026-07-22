"""CLI de descubrimiento (Entregable Fase 1 #2).

Ejecuta un escaneo real de la LAN e imprime el inventario por consola. Persiste
el resultado en la BD (para que la API sirva "datos reales"). Detecta y explica
la falta de Npcap/privilegios con claridad (requisito 7.2).

Uso:
    python -m agent.cli            # un escaneo, imprime tabla y guarda en BD
    python -m agent.cli --watch    # escaneo continuo (Ctrl+C para salir)
    python -m agent.cli --no-save  # no persistir, solo mostrar
    python -m agent.cli --interval 20
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from db.database import Database
from db.repositories import (
    AlertRepository,
    ConnectionEventRepository,
    DeviceRepository,
)

from .discovery import discover
from .interfaces import list_active_subnets
from .oui import shared_lookup
from .platform_checks import check_capabilities
from .scanner_service import ScannerService

RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
GREEN = "\033[32m"; YELLOW = "\033[33m"; RED = "\033[31m"; CYAN = "\033[36m"


def _c(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{RESET}"


def print_banner() -> None:
    print(_c("=" * 78, CYAN))
    print(_c("  Administrador de Conexiones LAN  —  Descubrimiento de dispositivos", BOLD))
    print(_c("=" * 78, CYAN))


def print_capabilities() -> bool:
    caps = check_capabilities()
    print(f"\n{_c('Plataforma:', BOLD)} {caps.platform}")
    admin = _c('SI', GREEN) if caps.is_admin else _c('NO', RED)
    npcap = _c('SI', GREEN) if caps.npcap else _c('NO', RED)
    print(f"{_c('Administrador:', BOLD)} {admin}    {_c('Npcap:', BOLD)} {npcap}    "
          f"{_c('Puede escanear:', BOLD)} {_c('SI', GREEN) if caps.can_scan else _c('NO', RED)}")
    for m in caps.messages:
        prefix = _c('  ->', YELLOW) if not caps.can_scan else _c('  ->', GREEN)
        print(f"{prefix} {m}")
    return caps.can_scan


def print_subnets() -> None:
    try:
        subs = list_active_subnets()
    except Exception as exc:
        print(_c(f"No se pudieron enumerar las interfaces: {exc}", RED))
        return
    print(f"\n{_c('Subredes activas a escanear:', BOLD)}")
    if not subs:
        print(_c("  (ninguna subred IPv4 activa detectada)", YELLOW))
    for s in subs:
        gw = f"  gw={s.gateway}" if s.gateway else ""
        print(f"  - {s.cidr:<20} iface={s.iface}  ip_local={s.local_ip}{gw}")


def print_table(devices) -> None:
    if not devices:
        print(_c("\n  No se detectaron dispositivos en este escaneo.", YELLOW))
        print(_c("  (Verifica Npcap, privilegios de admin y que estas conectado a la LAN.)", DIM))
        return
    print(f"\n{_c('Inventario (' + str(len(devices)) + ' dispositivos):', BOLD)}\n")
    header = f"{'IP':<16}{'MAC':<19}{'Fabricante':<26}{'Hostname':<22}{'Tipo':<22}"
    print(_c(header, BOLD))
    print(_c("-" * len(header), DIM))
    for d in devices:
        tags = []
        if d.is_gateway:
            tags.append(_c("[gateway]", CYAN))
        if d.is_self:
            tags.append(_c("[este equipo]", GREEN))
        vendor = (d.vendor or "-")[:24]
        host = (d.hostname or "-")[:20]
        dtype = (d.device_type or "Desconocido")[:20]
        line = f"{d.ip:<16}{d.mac:<19}{vendor:<26}{host:<22}{dtype:<22}"
        print(line + (" " + " ".join(tags) if tags else ""))


def persist(devices, db: Database) -> None:
    """Guarda el escaneo en la BD usando la misma logica del servicio."""
    svc = ScannerService(db)
    now = datetime.now(timezone.utc)
    dev_repo = DeviceRepository(db)
    ev_repo = ConnectionEventRepository(db)
    al_repo = AlertRepository(db)
    new_count = 0
    for d in devices:
        res = dev_repo.upsert_seen(
            mac=d.mac, ip=d.ip, hostname=d.hostname, vendor=d.vendor,
            device_type=d.device_type, is_random_mac=d.is_random_mac, seen_at=now,
        )
        if res.is_new:
            new_count += 1
            ev_repo.add(res.device_id, "connected", detail=f"IP {d.ip}", ts=now)
            al_repo.add("new_device",
                        f"Dispositivo nuevo: {d.hostname or d.vendor or d.mac} ({d.ip})",
                        device_id=res.device_id, severity="warning", ts=now)
    print(_c(f"\n  Guardado en BD: {db.path}", DIM))
    print(_c(f"  Total en inventario: {dev_repo.count()}  (nuevos en este escaneo: {new_count})", DIM))


def run_once(db: Database, save: bool, timeout: float) -> int:
    can_scan = print_capabilities()
    print_subnets()
    oui = shared_lookup()
    print(_c(f"\nBase OUI (IEEE) cargada: {oui.size} prefijos de fabricante.", DIM))
    if not can_scan:
        print(_c("\nNo se cumplen los requisitos para escanear. Corrige lo anterior y reintenta.", RED))
        # No abortamos con error duro: puede correrse en modo diagnostico.
    print(_c("\nEscaneando la red (ARP)... esto puede tardar unos segundos.", CYAN))
    try:
        devices = discover(timeout=timeout)
    except PermissionError as exc:
        print(_c(f"\nPermiso denegado: {exc}", RED))
        return 2
    except Exception as exc:
        print(_c(f"\nError durante el escaneo: {exc}", RED))
        return 2
    print_table(devices)
    if save:
        db.init()
        persist(devices, db)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Descubrimiento de dispositivos LAN")
    parser.add_argument("--watch", action="store_true", help="escaneo continuo")
    parser.add_argument("--interval", type=int, default=30, help="segundos entre escaneos (watch)")
    parser.add_argument("--no-save", action="store_true", help="no persistir en la BD")
    parser.add_argument("--timeout", type=float, default=3.0, help="timeout ARP por subred (s)")
    args = parser.parse_args(argv)

    print_banner()
    db = Database()
    save = not args.no_save

    if not args.watch:
        return run_once(db, save, args.timeout)

    print(_c(f"\nModo continuo (cada {args.interval}s). Ctrl+C para salir.", CYAN))
    try:
        while True:
            code = run_once(db, save, args.timeout)
            print(_c(f"\n[{datetime.now().strftime('%H:%M:%S')}] Esperando {args.interval}s...", DIM))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(_c("\nDetenido por el usuario.", YELLOW))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
