"""Servicio de escaneo periodico.

Orquesta el ciclo: descubrir -> persistir (upsert) -> calcular diferencias
(altas/bajas/cambios de IP) -> generar eventos y alertas -> notificar en vivo.

Inyeccion Quirurgica [Fase 2 + Fase 3 Real]: Lee y procesa las reglas horarias
aplicando el bloqueo ARP real de Scapy.
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
    RuleRepository, # 🆕 Agregamos el repositorio de reglas
)

from .discovery import DiscoveredDevice, discover
from .interfaces import list_active_subnets
from . import arp_cutter # 🆕 Conectamos nuestro motor quirúrgico secreto

log = logging.getLogger("lanmanager.scanner")

BroadcastFn = Callable[[dict], None]


class ScannerService:
    def __init__(
        self,
        db: Database,
        interval_seconds: int = 30,
        broadcast: Optional[BroadcastFn] = None,
        scan_timeout: float = 3.0,
        retention_days: int = 30,
        notifier=None,
        defense=None,
    ):
        self.db = db
        self.interval = max(5, int(interval_seconds))
        self.broadcast = broadcast
        self.scan_timeout = scan_timeout
        self.retention_days = max(1, int(retention_days))
        self.notifier = notifier   
        self.defense = defense     

        self.devices = DeviceRepository(db)
        self.events = ConnectionEventRepository(db)
        self.alerts = AlertRepository(db)
        self.rules = RuleRepository(db) # 🆕 Instanciamos el lector de reglas de la DB

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
        self._scheduler.add_job(
            self.prune_now, "interval", hours=24,
            id="retention_prune", max_instances=1, coalesce=True,
        )
        if self.defense is not None:
            self._scheduler.add_job(
                self.defense_check, "interval", minutes=2,
                id="defense_check", max_instances=1, coalesce=True,
            )
        self._scheduler.start()
        log.info("ScannerService iniciado con motor Scapy inyectado de forma automatica.")

    def prune_now(self) -> dict:
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

    def _notify(self, title: str, message: str) -> None:
        if self.notifier is not None:
            try:
                self.notifier.notify(title, message)
            except Exception:
                log.exception("Fallo al enviar notificacion")

    def defense_check(self) -> dict:
        if self.defense is None:
            return {}
        try:
            gw = next((s.gateway for s in list_active_subnets() if s.gateway), None)
            if not gw:
                return {}
            res = self.defense.check(gw)
            if res.get("spoofed"):
                msg = (f"Posible ARP spoofing del gateway {gw}: la MAC cambio de "
                       f"{res.get('baseline')} a {res.get('current')}.")
                self.alerts.add("arp_spoof_detected", msg, severity="critical")
                self._notify("ALERTA de seguridad", msg)
                log.warning(msg)
            return res
        except Exception as exc:
            log.exception("Fallo en defense_check: %s", exc)
            return {"error": str(exc)}

    def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
            log.info("ScannerService detenido")

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
        with self._lock:
            if self._scanning:
                return {"skipped": True, "reason": "escaneo en curso"}
            self._scanning = True
        try:
            scan_result = self._do_scan()
            # EL EVALUADOR DE HORARIOS DE CONTROL PARENTAL INMEDIATAMENTE DESPUÉS DEL ESCANEO:
            self._enforce_schedule_rules_now()
            return scan_result
        except Exception as exc:  
            self._last_error = str(exc)
            log.exception("Fallo en scan_once: %s", exc)
            return {"error": str(exc)}
        finally:
            self._scanning = False

    def _enforce_schedule_rules_now(self) -> None:
        """Revisa todas las reglas de horarios guardadas en SQLite y ejecuta el bloqueo si corresponde."""
        try:
            # Traer solo las reglas que el usuario marco como activas en el panel
            active_rules = self.rules.all(active_only=True)
            now_time_str = datetime.now().strftime("%H:%M") # Formato "HH:MM" local de tu PC (ej: "23:15")
            
            for rule in active_rules:
                if rule.get("rule_type") != "schedule":
                    continue
                    
                start = rule.get("schedule_start")
                end = rule.get("schedule_end")
                device_id = rule.get("device_id")
                
                if not start or not end or not device_id:
                    continue
                
                # Obtener la IP actual del dispositivo vinculado a la regla
                device_row = self.devices.get(device_id)
                if not device_row or not device_row.get("ip"):
                    continue
                    
                device_ip = device_row.get("ip")
                
                # Evaluar si la hora actual cae dentro del bloque prohibido configurado en la UI
                is_in_schedule = False
                if start <= end:
                    is_in_schedule = start <= now_time_str <= end
                else: # Reglas nocturnas cruzando la medianoche (ej: De 22:00 a 06:00)
                    is_in_schedule = now_time_str >= start or now_time_str <= end
                
                if is_in_schedule:
                    # El reloj de Windows marca hora de dormir -> Encendemos el hilo de Scapy
                    if not arp_cutter.ACTIVE_CUTS.get(device_ip, False):
                        log.info(f"[CRON REGLA]: Bloqueo automatico nocturno iniciado para {device_ip}")
                        arp_cutter.toggle_cut(device_ip, action=True)
                        self.devices.update_meta(device_id, is_blocked=True)
                else:
                    # Ya es de mañana o está fuera del horario prohibido -> Apagamos el hilo
                    if arp_cutter.ACTIVE_CUTS.get(device_ip, False):
                        log.info(f"[CRON REGLA]: Horario permitido alcanzado. Conexion restaurada para {device_ip}")
                        arp_cutter.toggle_cut(device_ip, action=False)
                        self.devices.update_meta(device_id, is_blocked=False)
        except Exception as e:
            log.error(f"[-] Error en el evaluador automatico de reglas: {e}")

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
                self._notify(
                    "Dispositivo nuevo en la red",
                    f"Se detecto un equipo nuevo: {label} ({d.ip} / {d.mac}).",
                )
            else:
                if d.mac not in self._online_macs:
                    self.events.add(
                        res.device_id,
                        "connected",
                        detail=f"IP {d.ip}",
                        ts=now,
                    )
                    summary["reconnected"].append(
                        {
                            "id": res.device_id,
                            "mac": d.mac,
                            "ip": d.ip,
                            "label": label,
                        }
                    )
                elif res.ip_changed:
                    self.events.add(
                        res.device_id,
                        "ip_changed",
                        detail=f"IP anterior {res.old_ip} -> {d.ip}",
                        ts=now,
                    )
                    summary["ip_changed"].append(
                        {
                            "id": res.device_id,
                            "mac": d.mac,
                            "ip": d.ip,
                            "label": label,
                        }
                    )

        # Marcamos la lista interna en memoria.
        self._online_macs = current_macs

        if self.broadcast is not None:
            try:
                self.broadcast(summary)
            except Exception:
                log.exception("Fallo al emitir el resumen del escaneo")

        return summary