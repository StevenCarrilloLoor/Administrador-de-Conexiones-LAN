"""Modelos Pydantic para la API (entrada/salida)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DeviceOut(BaseModel):
    id: int
    mac: str
    ip: Optional[str] = None
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    device_type: Optional[str] = None
    custom_name: Optional[str] = None
    device_group: Optional[str] = None
    is_random_mac: bool = False
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    is_blocked: bool = False
    bandwidth_limit_kbps: Optional[int] = None
    # derivados
    online: bool = False
    display_name: str = ""


class ConnectionEventOut(BaseModel):
    id: int
    device_id: int
    event_type: str
    detail: Optional[str] = None
    timestamp: str


class DeviceDetailOut(DeviceOut):
    history: list[ConnectionEventOut] = Field(default_factory=list)


class DeviceUpdateIn(BaseModel):
    custom_name: Optional[str] = None
    device_group: Optional[str] = None


class BlockIn(BaseModel):
    permanent: bool = True


class LimitIn(BaseModel):
    kbps: int = Field(gt=0, description="limite de ancho de banda en kbps")


class AlertOut(BaseModel):
    id: int
    alert_type: str
    device_id: Optional[int] = None
    message: str
    severity: str = "info"
    timestamp: str
    acknowledged: bool = False


class RuleOut(BaseModel):
    id: int
    device_id: Optional[int] = None
    device_group: Optional[str] = None
    rule_type: str
    limit_kbps: Optional[int] = None
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None
    days_of_week: Optional[str] = None
    active: bool = True
    created_at: str


class RuleIn(BaseModel):
    rule_type: str = Field(description="'block' | 'bandwidth_limit' | 'schedule'")
    device_id: Optional[int] = None
    device_group: Optional[str] = None
    limit_kbps: Optional[int] = None
    schedule_start: Optional[str] = None
    schedule_end: Optional[str] = None
    days_of_week: Optional[str] = None
    active: bool = True


class ScanResult(BaseModel):
    online_count: int
    new: list = Field(default_factory=list)
    reconnected: list = Field(default_factory=list)
    disconnected: list = Field(default_factory=list)
    ip_changed: list = Field(default_factory=list)
    scanned_subnets: list = Field(default_factory=list)
    timestamp: Optional[str] = None
