"""Tests de los repositorios (acceso a datos)."""
from datetime import datetime, timedelta, timezone

from db.repositories import iso


def test_upsert_new_then_update(repos):
    dev = repos["dev"]
    r1 = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", "h1", "Cisco Systems, Inc",
                         "Red (Cisco)", False)
    assert r1.is_new is True and r1.ip_changed is False
    r2 = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", "h1", "Cisco Systems, Inc",
                         "Red (Cisco)", False)
    assert r2.is_new is False and r2.ip_changed is False
    assert dev.count() == 1


def test_upsert_ip_change_detected(repos):
    dev = repos["dev"]
    dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    r = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.22", None, None, None, False)
    assert r.ip_changed is True
    assert r.previous_ip == "192.168.0.10" and r.new_ip == "192.168.0.22"


def test_upsert_does_not_null_out_vendor_hostname(repos):
    dev = repos["dev"]
    dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", "host1", "Cisco Systems, Inc",
                    "Red (Cisco)", False)
    # segunda observacion sin hostname/vendor no debe borrarlos
    dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    row = dev.get_by_mac("AA:BB:CC:11:22:33")
    assert row["vendor"] == "Cisco Systems, Inc"
    assert row["hostname"] == "host1"


def test_update_meta(repos):
    dev = repos["dev"]
    r = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    dev.update_meta(r.device_id, custom_name="PC de Steven", device_group="familia")
    row = dev.get(r.device_id)
    assert row["custom_name"] == "PC de Steven" and row["device_group"] == "familia"


def test_events_prune_old_only(repos):
    dev, ev = repos["dev"], repos["ev"]
    d = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    old = datetime.now(timezone.utc) - timedelta(days=40)
    ev.add(d.device_id, "connected", ts=old)
    ev.add(d.device_id, "connected")  # reciente
    pruned = ev.prune_older_than(30)
    assert pruned == 1
    assert len(ev.list_for_device(d.device_id)) == 1


def test_alerts_prune_keeps_unacknowledged(repos):
    dev, al = repos["dev"], repos["al"]
    d = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    old = datetime.now(timezone.utc) - timedelta(days=40)
    a_old_ack = al.add("new_device", "vieja vista", device_id=d.device_id, ts=old)
    al.acknowledge(a_old_ack)
    al.add("new_device", "vieja SIN ver", device_id=d.device_id, ts=old)  # no ack
    pruned = al.prune_older_than(30)
    assert pruned == 1  # solo borra la vieja YA vista
    assert al.unack_count() == 1  # la no leída se conserva aunque sea vieja


def test_rules_add_get_delete(repos):
    rule = repos["rule"]
    dev = repos["dev"]
    d = dev.upsert_seen("AA:BB:CC:11:22:33", "192.168.0.10", None, None, None, False)
    rid = rule.add("schedule", device_id=d.device_id, schedule_start="22:00", schedule_end="07:00")
    got = rule.get(rid)
    assert got is not None and got["rule_type"] == "schedule"
    assert rule.delete(rid) is True
    assert rule.get(rid) is None
    assert rule.delete(rid) is False  # ya no existe


def test_settings_roundtrip(repos):
    s = repos["set"]
    assert s.get("missing", "def") == "def"
    s.set("scan_interval", "45")
    assert s.get("scan_interval") == "45"
    s.set("scan_interval", "60")  # upsert
    assert s.get("scan_interval") == "60"
