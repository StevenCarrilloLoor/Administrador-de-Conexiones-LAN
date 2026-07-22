"""Fabrica de la aplicacion FastAPI.

Sirve la API REST, el WebSocket en vivo y el dashboard estatico desde el mismo
proceso (arquitectura agente + dashboard de la especificacion, seccion 2).
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from agent.arp_defense import ArpDefense
from agent.notifier import NotificationManager
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

from .auth import COOKIE_NAME, AuthService
from .config import Config
from .logging_setup import setup_logging
from .routers import alerts as alerts_router
from .routers import auth as auth_router
from .routers import devices as devices_router
from .routers import network as network_router
from .routers import rules as rules_router
from .routers import tools as tools_router
from .ws import ConnectionManager

# Rutas publicas (accesibles sin sesion): endpoints de auth y la pagina de login
# (que es autocontenida, con estilos inline).
_PUBLIC_PREFIXES = ("/api/auth/", "/login")
_PUBLIC_EXACT: set[str] = set()

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
        version="1.0.0",
        description=("Descubrimiento e inventario de la red local, con autenticacion, "
                     "reglas/horarios, notificaciones, utilidades (Wake-on-LAN, test de "
                     "velocidad, exportacion) y defensa anti-spoofing del propio equipo."),
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
    st.auth = AuthService(st.settings_repo)
    st.notifier = NotificationManager(st.settings_repo)
    st.defense = ArpDefense(st.settings_repo)
    st.capabilities = check_capabilities()
    st.ws = ConnectionManager()
    st.scanner = ScannerService(
        db, interval_seconds=cfg.scan_interval,
        broadcast=st.ws.broadcast_threadsafe, scan_timeout=cfg.scan_timeout,
        retention_days=cfg.retention_days, notifier=st.notifier, defense=st.defense,
    )

    for msg in st.capabilities.messages:
        (log.warning if not st.capabilities.can_scan else log.info)("Capacidad: %s", msg)
    if cfg.exposed_on_lan:
        log.warning(
            "El dashboard esta escuchando en %s (expuesto en la LAN) SIN autenticacion. "
            "La autenticacion es de Fase 3: no lo expongas hasta implementarla.", cfg.host,
        )

    # Middleware de autenticacion: protege API y dashboard. Deja pasar las rutas
    # publicas (login/setup/status y la pagina de login). [Fase 3]
    @app.middleware("http")
    async def _auth_guard(request: Request, call_next):
        if not cfg.auth_required:
            return await call_next(request)
        path = request.url.path
        if path in _PUBLIC_EXACT or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        if st.auth.verify_session_token(token):
            return await call_next(request)
        # No autenticado
        if path.startswith("/api") or path.startswith("/ws"):
            return JSONResponse({"detail": "No autenticado"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)

    # Routers
    app.include_router(auth_router.router)
    app.include_router(devices_router.router)
    app.include_router(rules_router.router)
    app.include_router(alerts_router.router)
    app.include_router(network_router.router)
    app.include_router(tools_router.router)

    @app.get("/api/status", tags=["status"])
    def status():
        caps = st.capabilities.as_dict()
        return {
            "app": "Administrador de Conexiones LAN",
            "version": app.version,
            "phase": 3,
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
                "auth_enabled": bool(cfg.auth_required),
                "auth_configured": st.auth.is_configured(),
            },
            "limitations": LIMITATIONS_ES,
        }

    @app.get("/api/stats/vendors", tags=["status"])
    def vendor_stats():
        return st.device_repo.vendor_breakdown()

    @app.get("/login", include_in_schema=False)
    def login_page():
        from fastapi.responses import FileResponse
        import os
        return FileResponse(os.path.join(cfg.dashboard_dir, "login.html"))

    @app.websocket("/ws/live")
    async def ws_live(ws: WebSocket):
        # Autenticacion del WebSocket por cookie (el middleware HTTP no cubre WS).
        if cfg.auth_required and not st.auth.verify_session_token(ws.cookies.get(COOKIE_NAME)):
            await ws.close(code=1008)  # policy violation
            return
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
    "El descubrimiento solo alcanza dispositivos del mismo segmento de red (misma LAN/Wi-Fi); no cruza VLANs.",
    "No detecta equipos si el router tiene aislamiento de clientes (AP client isolation) en el Wi-Fi.",
    "El escaneo puede ser parcial si el router usa ARP estatico o Dynamic ARP Inspection (redes gestionadas).",
    "Las reglas de bloqueo/limite/horario se registran como configuracion y eventos: el enforcement activo "
    "de trafico NO esta habilitado (se gestiona desde el router o de forma manual).",
    "La deteccion de 'equipo caido' depende del intervalo de escaneo y del TTL en linea: una caida muy breve "
    "puede no registrarse.",
    "La defensa anti-spoofing vigila y alerta sobre la tabla ARP de ESTE equipo; no protege a terceros ni "
    "bloquea al atacante (es defensiva, no ofensiva).",
    "Las notificaciones y el test de velocidad requieren salida a internet; sin conexion, se registran los fallos.",
]


# Para servir con uvicorn en modo factory:  uvicorn api.app:create_app --factory
# El punto de entrada normal es main.py, que construye la app una sola vez.
