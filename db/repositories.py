"""Capa de acceso a datos (repositorios).

Cada repositorio encapsula el SQL de una tabla. No hay logica de red aqui:
recibe datos ya normalizados por el agente y los persiste. Las marcas de tiempo
se almacenan como texto ISO-8601 en UTC.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .database import Database


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------------------
# Resultado de un upsert de escaneo
# ---------------------------------------------------------------------------
@dataclass
class UpsertResult:
    device_id: int
    is_new: bool
    ip_changed: bool
    previous_ip: Optional[str]
    new_ip: Optional[str]


class DeviceRepository:
    def __init__(self, db: Database):
        self.db = db

    def all(self) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
            return [dict(r) for r in rows]

    def get(self, device_id: int) -> Optional[dict]:
        with self.db.connect() as c:
            return row_to_dict(
                c.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
            )

    def get_by_mac(self, mac: str) -> Optional[dict]:
        with self.db.connect() as c:
            return row_to_dict(
                c.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
            )

    def count(self) -> int:
        with self.db.connect() as c:
            return int(c.execute("SELECT COUNT(*) FROM devices").fetchone()[0])

    def upsert_seen(
        self,
        mac: str,
        ip: Optional[str],
        hostname: Optional[str],
        vendor: Optional[str],
        device_type: Optional[str],
        is_random_mac: bool,
        seen_at: Optional[datetime] = None,
    ) -> UpsertResult:
        """Inserta o actualiza un dispositivo a partir de una observacion de escaneo.

        No sobreescribe hostname/vendor validos con valores nulos, ni pisa el
        vendor si ya existia (el OUI es estable). Devuelve si es nuevo y si cambio
        de IP para que el servicio de escaneo genere los eventos correspondientes.
        """
        now = seen_at or utcnow()
        now_s = iso(now)
        with self.db.connect() as c:
            existing = c.execute("SELECT * FROM devices WHERE mac = ?", (mac,)).fetchone()
            if existing is None:
                cur = c.execute(
                    """
                    INSERT INTO devices
                        (mac, ip, hostname, vendor, device_type, is_random_mac,
                         first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (mac, ip, hostname, vendor, device_type,
                     1 if is_random_mac else 0, now_s, now_s),
                )
                return UpsertResult(int(cur.lastrowid), True, False, None, ip)

            prev_ip = existing["ip"]
            ip_changed = bool(ip) and prev_ip != ip
            new_hostname = hostname or existing["hostname"]
            new_vendor = existing["vendor"] or vendor
            new_type = device_type or existing["device_type"]
            c.execute(
                """
                UPDATE devices
                   SET ip = COALESCE(?, ip),
                       hostname = ?,
                       vendor = ?,
                       device_type = ?,
                       last_seen = ?
                 WHERE id = ?
                """,
                (ip, new_hostname, new_vendor, new_type, now_s, existing["id"]),
            )
            return UpsertResult(int(existing["id"]), False, ip_changed, prev_ip, ip)

    def update_meta(
        self,
        device_id: int,
        custom_name: Optional[str] = None,
        device_group: Optional[str] = None,
    ) -> Optional[dict]:
        sets, params = [], []
        if custom_name is not None:
            sets.append("custom_name = ?"); params.append(custom_name or None)
        if device_group is not None:
            sets.append("device_group = ?"); params.append(device_group or None)
        if not sets:
            return self.get(device_id)
        params.append(device_id)
        with self.db.connect() as c:
            c.execute(f"UPDATE devices SET {', '.join(sets)} WHERE id = ?", params)
        return self.get(device_id)

    def set_blocked(self, device_id: int, blocked: bool) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE devices SET is_blocked = ? WHERE id = ?",
                      (1 if blocked else 0, device_id))

    def set_bandwidth_limit(self, device_id: int, kbps: Optional[int]) -> None:
        with self.db.connect() as c:
            c.execute("UPDATE devices SET bandwidth_limit_kbps = ? WHERE id = ?",
                      (kbps, device_id))

    def vendor_breakdown(self) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                """
                SELECT COALESCE(vendor, 'Desconocido') AS vendor, COUNT(*) AS n
                  FROM devices GROUP BY COALESCE(vendor, 'Desconocido')
                 ORDER BY n DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]


class ConnectionEventRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, device_id: int, event_type: str,
            detail: Optional[str] = None, ts: Optional[datetime] = None) -> int:
        with self.db.connect() as c:
            cur = c.execute(
                "INSERT INTO connection_events (device_id, event_type, detail, timestamp)"
                " VALUES (?, ?, ?, ?)",
                (device_id, event_type, detail, iso(ts or utcnow())),
            )
            return int(cur.lastrowid)

    def list_for_device(self, device_id: int, limit: int = 100) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM connection_events WHERE device_id = ?"
                " ORDER BY timestamp DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def recent(self, limit: int = 200) -> list[dict]:
        with self.db.connect() as c:
            rows = c.execute(
                "SELECT * FROM connection_events ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]


class AlertRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, alert_type: str, message: str, device_id: Optional[int] = None,
            severity: str = "info", ts: Optional[datetime] = None) -> int:
        with self.db.connect() as c:
            cur = c.execute(
                "INSERT INTO alerts (alert_type, device_id, message, severity, timestamp)"
                " VALUES (?, ?, ?, ?, ?)",
                (alert_type, device_id, message, severity, iso(ts or utcnow())),
            )
            return int(cur.lastrowid)

    def list_recent(self, limit: int = 100, include_ack: bool = True) -> list[dict]:
        q = "SELECT * FROM alerts"
        if not include_ack:
            q += " WHERE acknowledged = 0"
        q += " ORDER BY timestamp DESC LIMIT ?"
        with self.db.connect() as c:
            return [dict(r) for r in c.execute(q, (limit,)).fetchall()]

    def acknowledge(self, alert_id: int) -> bool:
        with self.db.connect() as c:
            cur = c.execute("UPDATE alerts SET acknowledged = 1 WHERE id = ?", (alert_id,))
            return cur.rowcount > 0

    def unack_count(self) -> int:
        with self.db.connect() as c:
            return int(c.execute("SELECT COUNT(*) FROM alerts WHERE acknowledged = 0").fetchone()[0])


class RuleRepository:
    def __init__(self, db: Database):
        self.db = db

    def add(self, rule_type: str, device_id: Optional[int] = None,
            device_group: Optional[str] = None, limit_kbps: Optional[int] = None,
            schedule_start: Optional[str] = None, schedule_end: Optional[str] = None,
            days_of_week: Optional[str] = None, active: bool = True) -> int:
        with self.db.connect() as c:
            cur = c.execute(
                """
                INSERT INTO rules
                    (device_id, device_group, rule_type, limit_kbps,
                     schedule_start, schedule_end, days_of_week, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, device_group, rule_type, limit_kbps,
                 schedule_start, schedule_end, days_of_week,
                 1 if active else 0, iso(utcnow())),
            )
            return int(cur.lastrowid)

    def all(self, active_only: bool = False) -> list[dict]:
        q = "SELECT * FROM rules"
        if active_only:
            q += " WHERE active = 1"
        q += " ORDER BY created_at DESC"
        with self.db.connect() as c:
            return [dict(r) for r in c.execute(q).fetchall()]

    def delete(self, rule_id: int) -> bool:
        with self.db.connect() as c:
            cur = c.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            return cur.rowcount > 0


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        with self.db.connect() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def set(self, key: str, value: str) -> None:
        with self.db.connect() as c:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    def all(self) -> dict:
        with self.db.connect() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings").fetchall()}
