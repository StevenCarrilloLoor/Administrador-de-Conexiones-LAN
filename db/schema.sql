-- ============================================================================
-- Administrador de Conexiones LAN — Esquema de base de datos (SQLite)
-- Fase 1: descubrimiento e inventario.
--
-- Fiel al modelo de datos sugerido en la especificacion (seccion 5), con dos
-- extensiones documentadas y compatibles:
--   * devices.device_type  -> requerido por "inferir tipo de dispositivo" (Fase 1)
--   * devices.is_random_mac -> marca MAC localmente administrada / aleatoria
-- Ademas se agregan indices y claves foraneas para integridad y rendimiento.
-- El script es idempotente (CREATE TABLE IF NOT EXISTS): se puede re-ejecutar.
-- ============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Inventario de dispositivos (uno por MAC, identificador estable en la LAN)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    mac                   TEXT UNIQUE NOT NULL,          -- normalizada AA:BB:CC:DD:EE:FF
    ip                    TEXT,                          -- ultima IPv4 vista
    hostname              TEXT,                          -- si resuelve por DNS/NetBIOS
    vendor                TEXT,                          -- fabricante por OUI (IEEE)
    device_type           TEXT,                          -- tipo inferido (heuristico)
    custom_name           TEXT,                          -- etiqueta manual del usuario
    device_group          TEXT,                          -- agrupacion manual (IoT, familia...)
    is_random_mac         INTEGER NOT NULL DEFAULT 0,    -- 1 = MAC localmente administrada
    first_seen            DATETIME,                      -- primera vez visto (UTC ISO-8601)
    last_seen             DATETIME,                      -- ultima vez visto (UTC ISO-8601)
    is_blocked            INTEGER NOT NULL DEFAULT 0,    -- estado de bloqueo (enforce: Fase 2)
    bandwidth_limit_kbps  INTEGER                        -- limite de ancho de banda (Fase 2)
);

CREATE INDEX IF NOT EXISTS idx_devices_ip        ON devices(ip);
CREATE INDEX IF NOT EXISTS idx_devices_last_seen ON devices(last_seen);
CREATE INDEX IF NOT EXISTS idx_devices_group     ON devices(device_group);

-- ---------------------------------------------------------------------------
-- Historial de eventos de conexion (altas, bajas, cambios de IP)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS connection_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id   INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    event_type  TEXT NOT NULL,   -- 'connected' | 'disconnected' | 'ip_changed'
    detail      TEXT,            -- info opcional (p. ej. "192.168.0.10 -> 192.168.0.22")
    timestamp   DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_device ON connection_events(device_id);
CREATE INDEX IF NOT EXISTS idx_events_time   ON connection_events(timestamp);

-- ---------------------------------------------------------------------------
-- Reglas (bloqueos, limites, horarios). Enforcement activo: Fase 2.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id      INTEGER REFERENCES devices(id) ON DELETE CASCADE,
    device_group   TEXT,            -- regla por grupo (alternativa a device_id)
    rule_type      TEXT NOT NULL,   -- 'block' | 'bandwidth_limit' | 'schedule'
    limit_kbps     INTEGER,         -- para 'bandwidth_limit'
    schedule_start TEXT,            -- 'HH:MM', nullable
    schedule_end   TEXT,            -- 'HH:MM', nullable
    days_of_week   TEXT,            -- CSV '0..6' (0=lunes), nullable = todos los dias
    active         INTEGER NOT NULL DEFAULT 1,
    created_at     DATETIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rules_device ON rules(device_id);
CREATE INDEX IF NOT EXISTS idx_rules_active ON rules(active);

-- ---------------------------------------------------------------------------
-- Alertas (dispositivo nuevo, caida inesperada, deteccion de spoofing)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_type    TEXT NOT NULL,   -- 'new_device' | 'device_down' | 'arp_spoof_detected'
    device_id     INTEGER REFERENCES devices(id) ON DELETE SET NULL,
    message       TEXT NOT NULL,
    severity      TEXT NOT NULL DEFAULT 'info',   -- 'info' | 'warning' | 'critical'
    timestamp     DATETIME NOT NULL,
    acknowledged  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_time ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_ack  ON alerts(acknowledged);

-- ---------------------------------------------------------------------------
-- Configuracion clave/valor (persistencia de ajustes)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);
