"""Servicio de escaneo periodico.

Orquesta el ciclo: descubrir -> persistir (upsert) -> calcular diferencias
(altas/bajas/cambios de IP) -> generar eventos y alertas -> notificar en vivo.

El estado "en linea" se calcula por diferencia en memoria entre escaneos
consecutivos (preciso durante la ejecucion) y ademas se deriva de `last_seen`
en la API (robusto ante reinicios).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler

from db.database import Database
from db.repositories import (
    AlertRepository,
    ConnectionEventRepository,
    DeviceRepository,
)

from .discovery import DiscoveredDevice, discover
from .interfaces import list_active_subnets

log = logging.getLogger("lanmanager.scanner")

# Callback para difundir novedades (lo conecta la API al WebSocket)
BroadcastFn = Callable[[dict], None]


class ScannerService:
    def __init__(
        self,
        db: Database,
        interval_seconds: int = 30,
        broadcast: Optional[BroadcastFn] = None,
        scan_timeout: float = 3.0,
        retention_days: int = 30,
    ):
        self.db = db
        self.interval = max(5, int(interval_seconds))
        self.broadcast = broadcast
        self.scan_timeout = scan_timeout
        self.retention_days = max(1, int(retention_days))

        self.devices = DeviceRepository(db)
        self.events = ConnectionEventRepository(db)
        self.alerts = AlertRepository(db)

        self._online_macs: set[str] = set()
        self._lock = threading.Lock()
        self._scheduler: Optional[BackgroundScheduler] = None
        self._last_scan_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._scanning = False

    # -- ciclo de vida -------------------------------------------------------
    def start(self) -> None:
        if self._scheduler is not None:
            return
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.add_job(
            self.scan_once, "interval", seconds=self.interval,
            id="periodic_scan", max_instances=1, coalesce=True,
            next_run_time=datetime.now(timezone.utc),
        )
        # Retencion: purga diaria de historial viejo + VACUUM. [M2]
        self._scheduler.add_job(
            self.prune_now, "interval", hours=24,
            id="retention_prune", max_instances=1, coalesce=True,
        )
        self._scheduler.start()
        log.info("ScannerService iniciado (intervalo=%ss, retencion=%sd)",
                 self.interval, self.retention_days)

    def prune_now(self) -> dict:
        """Purga eventos/alertas mas viejos que retention_days y compacta la BD. [M2]"""
        try:
            ev = self.events.prune_older_than(self.retention_days)
            al = self.alerts.prune_older_than(self.retention_days)
            if ev or al:
                self.db.vacuum()
            log.info("Retencion: %d eventos y %d alertas purgados (> %sd)",
                     ev, al, self.retention_days)
            return {"events_pruned": ev, "alerts_pruned": al}
        except Exception as exc:
            log.exception("Fallo en la purga de retencion: %s", exc)
            return {"error": str(exc)}

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            log.info("ScannerService detenido")

    # -- estado --------------------------------------------------------------
    @property
    def status(self) -> dict:
        return {
            "interval_seconds": self.interval,
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "online_count": len(self._online_macs),
            "last_error": self._last_error,
            "scanning": self._scanning,
        }

    # -- escaneo -------------------------------------------------------------
    def scan_once(self) -> dict:
        """Ejecuta un escaneo, reconcilia con la BD y difunde el resultado."""
        with self._lock:
            if self._scanning:
                return {"skipped": True, "reason": "escaneo en curso"}
            self._scanning = True
        try:
            return self._do_scan()
        except Exception as exc:  # nunca romper el scheduler
            self._last_error = str(exc)
            log.exception("Fallo en scan_once: %s", exc)
            return {"error": str(exc)}
        finally:
            self._scanning = False

    def _do_scan(self) -> dict:
        subnets = list_active_subnets()
        discovered: list[DiscoveredDevice] = discover(
            subnets=subnets, timeout=self.scan_timeout
        )
        now = datetime.now(timezone.utc)
        self._last_scan_at = now
        self._last_error = None

        current_macs = {d.mac for d in discovered}
        summary = {
            "new": [], "reconnected": [], "disconnected": [],
            "ip_changed": [], "online_count": len(current_macs),
            "scanned_subnets": [s.as_dict() for s in subnets],
            "timestamp": now.isoformat(),
        }

        for d in discovered:
            res = self.devices.upsert_seen(
                mac=d.mac, ip=d.ip, hostname=d.hostname, vendor=d.vendor,
                device_type=d.device_type, is_random_mac=d.is_random_mac, seen_at=now,
            )
            label = d.hostname or d.vendor or d.mac
            if res.is_new:
                self.events.add(res.device_id, "connected", detail=f"IP {d.ip}", ts=now)
                self.alerts.add(
                    "new_device",
                    f"Dispositivo nuevo detectado: {label} ({d.ip} / {d.mac})",
                    device_id=res.device_id, severity="warning", ts=now,
                )
                summary["new"].append({"id": res.device_id, "mac": d.mac,
                                       "ip": d.ip, "label": label})
            else:
                if d.mac not in self._online_macs:
                    self.events.add(res.device_id, "connected", detail=f"IP {d.ip}", ts=now)
                    summary["reconnected"].append({"id": res.device_id, "mac": d.mac,
                                                   "ip": d.ip, "label": label})
                if res.ip_changed:
                    self.events.add(
                        res.device_id, "ip_changed",
                        detail=f"{res.previous_ip} -> {res.new_ip}", ts=now,
                    )
                    summary["ip_changed"].append({"id": res.device_id, "mac": d.mac,
                                                  "from": res.previous_ip, "to": res.new_ip})

        # Bajas: estaban en linea y ya no aparecen
        gone = self._online_macs - current_macs
        for mac in gone:
            dev = self.devices.get_by_mac(mac)
            if dev:
                self.events.add(dev["id"], "disconnected", ts=now)
                summary["disconnected"].append({"id": dev["id"], "mac": mac,
                                                "label": dev.get("custom_name") or dev.get("hostname") or mac})

        self._online_macs = current_macs

        log.info(
            "Escaneo: %d en linea (nuevos=%d, reconectados=%d, bajas=%d, ip_cambiada=%d)",
            len(current_macs), len(summary["new"]), len(summary["reconnected"]),
            len(summary["disconnected"]), len(summary["ip_changed"]),
        )

        if self.broadcast:
            try:
                self.broadcast({"type": "scan", "data": summary})
            except Exception:
                log.exception("Fallo al difundir el resultado del escaneo")

        return summary

    def online_macs(self) -> set[str]:
        return set(self._online_macs)
