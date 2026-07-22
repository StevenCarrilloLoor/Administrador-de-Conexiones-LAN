"""Launcher de AdministradorLAN.exe.

Flujo al iniciar (el .exe pide elevacion via manifiesto requireAdministrator):
  1. Verificar si Npcap esta instalado.
  2. Si falta: descargar el instalador OFICIAL de npcap.com y lanzarlo; esperar a
     que el usuario complete los 2-3 clics estandar y continuar automaticamente.
  3. Arrancar el servidor FastAPI (API + WebSocket + dashboard) en un hilo.
  4. Abrir el navegador en http://localhost:8080 cuando el servidor este listo.
  5. Mostrar un icono en la bandeja del sistema con 'Abrir dashboard' y 'Salir'.

Modo de prueba no interactivo:  AdministradorLAN.exe --selftest
  (o python launcher.py --selftest): arranca el servidor, comprueba /api/status y
  sale con codigo 0/1, sin dialogos, sin navegador y sin bandeja.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Asegurar la raiz del proyecto en sys.path (modo codigo fuente)
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import apppaths  # noqa: E402

log = logging.getLogger("lanmanager.launcher")


# --------------------------------------------------------------------------- #
# Utilidades de UI (MessageBox nativo, sin dependencias)
# --------------------------------------------------------------------------- #
MB_OK = 0x0
MB_OKCANCEL = 0x1
MB_ICONERROR = 0x10
MB_ICONQUESTION = 0x20
MB_ICONWARNING = 0x30
MB_ICONINFO = 0x40
IDOK = 1


def message_box(text: str, title: str = "Administrador de Conexiones LAN",
                style: int = MB_OK) -> int:
    try:
        import ctypes
        return int(ctypes.windll.user32.MessageBoxW(0, text, title, style))
    except Exception:
        _safe_print(f"[{title}] {text}")
        return IDOK


def _safe_print(msg: str) -> None:
    try:
        if sys.stdout is not None:
            print(msg, flush=True)
    except Exception:
        pass


def setup_launcher_logging() -> None:
    # Handler propio en el logger "lanmanager.launcher" (NO en el root "lanmanager"),
    # para que setup_logging() de la app no lo borre y launcher.log conserve la traza
    # del launcher aunque el servidor arranque despues. [B3]
    try:
        logdir = apppaths.log_dir()
        h = logging.FileHandler(logdir / "launcher.log", encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        launcher_logger = logging.getLogger("lanmanager.launcher")
        launcher_logger.setLevel(logging.INFO)
        launcher_logger.addHandler(h)
        logging.getLogger("lanmanager").setLevel(logging.INFO)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Npcap
# --------------------------------------------------------------------------- #
def ensure_npcap() -> bool:
    """Garantiza Npcap; si falta, guia la instalacion oficial. Devuelve True si quedo listo."""
    from agent.platform_checks import npcap_installed
    if npcap_installed():
        log.info("Npcap ya esta instalado.")
        return True

    r = message_box(
        "Este programa necesita Npcap, el driver de captura de red de Windows "
        "(el mismo que usa Wireshark).\n\n"
        "Se descargara el instalador OFICIAL desde npcap.com y se abrira. "
        "Segui los 2-3 pasos del instalador de Npcap y DEJA MARCADA la opcion "
        "'Install Npcap in WinPcap API-compatible Mode'.\n\n"
        "El programa continuara solo cuando termine la instalacion.\n\n"
        "Descargar e instalar Npcap ahora?",
        style=MB_OKCANCEL | MB_ICONQUESTION,
    )
    if r != IDOK:
        message_box(
            "Se continuara SIN Npcap. El panel se abrira igual, pero no podra escanear "
            "la red hasta instalar Npcap (podes hacerlo despues desde https://npcap.com).",
            style=MB_ICONWARNING,
        )
        return False

    import tempfile
    from agent import npcap_bootstrap as nb
    try:
        log.info("Descargando instalador de Npcap...")
        installer = nb.download_installer(tempfile.gettempdir())
        log.info("Instalador descargado: %s", installer)
    except Exception as exc:
        log.exception("Fallo la descarga de Npcap")
        message_box(
            "No se pudo descargar Npcap automaticamente.\n\n"
            "Instalalo manualmente desde https://npcap.com/#download y volve a abrir el programa.\n\n"
            f"Detalle: {exc}",
            style=MB_ICONERROR,
        )
        return False

    # Verificar la firma Authenticode antes de ejecutar un binario con privilegios. [M3]
    ok_sig, detail = nb.verify_installer_signature(installer)
    log.info("Firma del instalador de Npcap: %s", detail)
    if not ok_sig:
        message_box(
            "No se pudo verificar la firma digital del instalador de Npcap "
            f"({detail}).\n\nPor seguridad NO se ejecutara automaticamente. "
            "Instalalo manualmente desde https://npcap.com/#download.",
            style=MB_ICONERROR,
        )
        return False

    message_box(
        "Se abrira el instalador de Npcap. Completá los pasos (Aceptar la licencia -> "
        "Install -> Finish) dejando marcada la opcion 'WinPcap API-compatible Mode'.\n\n"
        "Cuando termines, este programa seguira automaticamente.",
        style=MB_ICONINFO,
    )
    ok = nb.launch_installer_and_wait(installer)
    if ok:
        log.info("Npcap instalado correctamente.")
        message_box("Npcap se instalo correctamente. El panel ya podra escanear la red.",
                    style=MB_ICONINFO)
    else:
        log.warning("Npcap no quedo instalado tras la espera.")
        message_box(
            "No se detecto Npcap instalado. Se continuara sin escaneo de red. "
            "Podes reintentar cerrando y volviendo a abrir el programa.",
            style=MB_ICONWARNING,
        )
    return ok


# --------------------------------------------------------------------------- #
# Servidor
# --------------------------------------------------------------------------- #
def start_server(cfg):
    import uvicorn
    from api.app import create_app

    app = create_app(cfg)
    server = uvicorn.Server(uvicorn.Config(
        app, host=cfg.host, port=cfg.port, log_level="info",
    ))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def wait_until_ready(cfg, timeout: float = 40.0) -> bool:
    url = f"http://127.0.0.1:{cfg.port}/api/status"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def dashboard_url(cfg) -> str:
    # 0.0.0.0 / :: no son direccionables por el navegador: usar localhost para abrir. [M11]
    host = cfg.host
    if host in ("0.0.0.0", "::", ""):
        host = "localhost"
    return f"http://{host}:{cfg.port}/"


# --------------------------------------------------------------------------- #
# Bandeja del sistema
# --------------------------------------------------------------------------- #
def make_tray_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (14, 20, 32, 255))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), outline=(61, 139, 255, 255), width=3)
    d.ellipse((22, 22, 42, 42), outline=(61, 139, 255, 180), width=2)
    d.ellipse((28, 28, 36, 36), fill=(55, 214, 122, 255))
    d.line((32, 32, 52, 14), fill=(61, 139, 255, 255), width=2)
    return img


def run_tray(cfg, server) -> None:
    try:
        import pystray
    except Exception:
        log.warning("pystray no disponible; el servidor sigue corriendo. Ctrl+C para salir.")
        try:
            while not server.should_exit:
                time.sleep(1)
        except KeyboardInterrupt:
            server.should_exit = True
        return

    def on_open(icon, item):
        webbrowser.open(dashboard_url(cfg))

    def on_quit(icon, item):
        log.info("Cerrando por peticion del usuario (bandeja).")
        server.should_exit = True
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir dashboard", on_open, default=True),
        pystray.MenuItem("Salir", on_quit),
    )
    icon = pystray.Icon("AdministradorLAN", make_tray_image(),
                        "Administrador de Conexiones LAN", menu)
    icon.run()


# --------------------------------------------------------------------------- #
# Modos de ejecucion
# --------------------------------------------------------------------------- #
def selftest() -> int:
    """Prueba no interactiva: arranca el servidor y verifica /api/status."""
    try:
        return _selftest_inner()
    except Exception as exc:  # registrar cualquier fallo de arranque para diagnostico
        import traceback
        tb = traceback.format_exc()
        _safe_print("RESULTADO SELFTEST: ERROR\n" + tb)
        try:
            (apppaths.log_dir() / "selftest_result.txt").write_text(
                "RESULTADO SELFTEST: ERROR\n" + tb, encoding="utf-8")
        except Exception:
            pass
        return 1


def _selftest_inner() -> int:
    from api.config import Config
    cfg = Config.load()
    cfg.auto_scan = False
    _safe_print(f"[selftest] arrancando servidor en 127.0.0.1:{cfg.port} ...")
    server, _ = start_server(cfg)
    ok = wait_until_ready(cfg, timeout=40)
    _safe_print(f"[selftest] servidor listo: {ok}")
    if ok:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/api/status", timeout=3) as r:
                _safe_print(f"[selftest] /api/status -> {r.status}")
        except Exception as e:
            _safe_print(f"[selftest] error consultando status: {e}")
            ok = False
    server.should_exit = True
    time.sleep(1)
    result = "RESULTADO SELFTEST: " + ("OK" if ok else "ERROR")
    _safe_print(result)
    # Escribir tambien a archivo (util cuando el .exe es windowed y no hay consola)
    try:
        (apppaths.log_dir() / "selftest_result.txt").write_text(
            f"{result}\nfrozen={apppaths.is_frozen()}\n"
            f"dashboard_exists={apppaths.dashboard_dir().exists()}\n"
            f"oui_exists={apppaths.oui_csv_path().exists()}\n",
            encoding="utf-8",
        )
    except Exception:
        pass
    return 0 if ok else 1


def main() -> int:
    setup_launcher_logging()
    if "--selftest" in sys.argv:
        return selftest()

    try:
        from api.config import Config
        cfg = Config.load()
        log.info("Iniciando AdministradorLAN (host=%s port=%s)", cfg.host, cfg.port)

        ensure_npcap()

        server, _ = start_server(cfg)
        if wait_until_ready(cfg):
            log.info("Servidor listo; abriendo navegador.")
            webbrowser.open(dashboard_url(cfg))
        else:
            message_box(
                "El servidor no respondio a tiempo. Revisa logs\\launcher.log y logs\\app.log "
                "junto al ejecutable.",
                style=MB_ICONWARNING,
            )

        run_tray(cfg, server)
        return 0
    except Exception as exc:
        log.exception("Error fatal en el launcher")
        message_box(f"Error inesperado al iniciar:\n\n{exc}\n\n"
                    "Revisa logs\\launcher.log junto al ejecutable.",
                    style=MB_ICONERROR)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
