"""Fabrica de la aplicacion FastAPI.

Sirve la API REST, el WebSocket en vivo y el dashboard estatico desde el mismo
proceso (arquitectura agente + dashboard de la especificacion, seccion 2).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from agent.oui import shared_lookup
from agent.platform_checks import check_capabilities
from agent.scanner_service import ScannerService
from db.database import Database
from db.repositories import (
    AlertRepository,
    ConnectionEventRepository,
    DeviceRepository,
    RuleRepository,
    SettingsRepository,
)

from .config import Config
from .logging_setup import setup_logging
from .routers import alerts as alerts_router
from .routers import devices as devices_router
from .routers import network as network_router
from .routers import rules as rules_router
from .ws import ConnectionManager

log = logging.getLogger("lanmanager.api")


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or Config.load()
    setup_logging(cfg.log_dir)
    log.info("Iniciando Administrador de Conexiones LAN")

    db = Database(cfg.db_path)
    db.init()
    oui = shared_lookup()
    log.info("Base OUI cargada: %d prefijos", oui.size)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # startup
        app.state.ws.bind_loop(asyncio.get_running_loop())
        if cfg.auto_scan:
            if app.state.capabilities.can_scan:
                app.state.scanner.start()
                log.info("Escaneo automatico iniciado")
            else:
                log.warning("Escaneo automatico NO iniciado: faltan requisitos "
                            "(ver /api/status). Instala Npcap y ejecuta como administrador.")
        try:
            yield
        finally:
            # shutdown
            app.state.scanner.stop()

    app = FastAPI(
        title="Administrador de Conexiones LAN",
        version="1.0.0-fase1",
        description="Descubrimiento e inventario de dispositivos en la red local (Fase 1).",
        lifespan=lifespan,
    )
    # Sin CORS: el dashboard se sirve desde el MISMO origen que la API (app.mount("/")),
    # asi que no se necesita CORS. No habilitar comodin cross-origin en un servicio local
    # sin autenticacion (evita que cualquier web lea/modifique el inventario). [B1]

    # Estado compartido
    st = app.state
    st.config = cfg
    st.db = db
    st.device_repo = DeviceRepository(db)
    st.event_repo = ConnectionEventRepository(db)
    st.alert_repo = AlertRepository(db)
    st.rule_repo = RuleRepository(db)
    st.settings_repo = SettingsRepository(db)
    st.capabilities = check_capabilities()
    st.ws = ConnectionManager()
    st.scanner = ScannerService(
        db, interval_seconds=cfg.scan_interval,
        broadcast=st.ws.broadcast_threadsafe, scan_timeout=cfg.scan_timeout,
        retention_days=cfg.retention_days,
    )

    for msg in st.capabilities.messages:
        (log.warning if not st.capabilities.can_scan else log.info)("Capacidad: %s", msg)
    if cfg.exposed_on_lan:
        log.warning(
            "El dashboard esta escuchando en %s (expuesto en la LAN) SIN autenticacion. "
            "La autenticacion es de Fase 3: no lo expongas hasta implementarla.", cfg.host,
        )

    # Routers
    app.include_router(devices_router.router)
    app.include_router(rules_router.router)
    app.include_router(alerts_router.router)
    app.include_router(network_router.router)

    @app.get("/api/status", tags=["status"])
    def status():
        caps = st.capabilities.as_dict()
        return {
            "app": "Administrador de Conexiones LAN",
            "version": app.version,
            "phase": 1,
            "capabilities": caps,
            "scanner": st.scanner.status,
            "counts": {
                "devices": st.device_repo.count(),
                "alerts_unack": st.alert_repo.unack_count(),
                "rules": len(st.rule_repo.all()),
            },
            "oui_prefixes": oui.size,
            "config": {
                "host": cfg.host, "port": cfg.port,
                "scan_interval": cfg.scan_interval, "online_ttl": cfg.online_ttl,
                "exposed_on_lan": cfg.exposed_on_lan,
                "auth_enabled": False,  # Fase 3
            },
            "limitations": LIMITATIONS_ES,
        }

    @app.get("/api/stats/vendors", tags=["status"])
    def vendor_stats():
        return st.device_repo.vendor_breakdown()

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        await st.ws.connect(ws)
        try:
            # Estado inicial al conectar. La lectura SQLite (bloqueante) va a un
            # threadpool para no bloquear el event loop. [M4]
            rows = await run_in_threadpool(st.device_repo.all)
            await ws.send_json({"type": "hello", "data": {
                "devices": [devices_router.to_device_out(r, cfg.online_ttl) for r in rows],
                "scanner": st.scanner.status,
            }})
            while True:
                # Mantener viva la conexion; el cliente puede enviar pings
                await ws.receive_text()
        except WebSocketDisconnect:
            await st.ws.disconnect(ws)
        except Exception:
            await st.ws.disconnect(ws)

    # Dashboard estatico (montado al final para no tapar las rutas de la API)
    app.mount("/", StaticFiles(directory=cfg.dashboard_dir, html=True), name="dashboard")

    return app


LIMITATIONS_ES = [
    "Solo funciona contra dispositivos del mismo segmento de red (misma LAN/Wi-Fi); no cruza VLANs.",
    "No funciona si el router tiene aislamiento de clientes (AP client isolation) en el Wi-Fi.",
    "No funciona si el router usa ARP estatico o Dynamic ARP Inspection (comun en redes de oficina gestionadas).",
    "El bloqueo/limite (Fase 2) deja de aplicarse si este equipo se apaga, suspende o se cierra el proceso.",
    "El antivirus/firewall del dispositivo objetivo puede detectar el spoofing (misma tecnica base que un MITM).",
]


# Para servir con uvicorn en modo factory:  uvicorn api.app:create_app --factory
# El punto de entrada normal es main.py, que construye la app una sola vez.
