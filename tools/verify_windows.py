"""Verificacion end-to-end en Windows: levanta el servidor REAL y lo prueba por HTTP.

A diferencia de una prueba con TestClient (que exige httpx), aqui se arranca el
servidor Uvicorn de verdad en un hilo y se lo consulta con urllib (biblioteca
estandar). Es la prueba mas representativa: el mismo servidor que usa el usuario.

Escribe un reporte legible que run_verify.bat guarda en logs\\verify.log. Los
dispositivos reales encontrados dependen de Npcap + privilegios de administrador;
si faltan, el reporte lo indica con claridad (verifica el requisito 7.2).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# BD temporal para no tocar la real durante la verificacion
os.environ["LANMGR_AUTO_SCAN"] = "false"
_tmp_db = ROOT / "data" / "verify_tmp.db"
os.environ["LANMGR_DB_PATH"] = str(_tmp_db)
for _suffix in ("", "-wal", "-shm"):
    _p = Path(str(_tmp_db) + _suffix)
    try:
        if _p.exists():
            _p.unlink()
    except Exception:
        pass

HOST = "127.0.0.1"
PORT = 8765
BASE = f"http://{HOST}:{PORT}"


def req(path: str, method: str = "GET", timeout: float = 15.0):
    r = urllib.request.Request(
        BASE + path, method=method,
        data=b"" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return None, str(e).encode()


def main() -> int:
    print("=" * 72)
    print(" Verificacion en Windows (servidor REAL) - Administrador de Conexiones LAN")
    print("=" * 72)

    from agent.platform_checks import check_capabilities
    caps = check_capabilities()
    print(f"Plataforma      : {caps.platform}")
    print(f"Administrador   : {caps.is_admin}")
    print(f"Npcap instalado : {caps.npcap}")
    print(f"Puede escanear  : {caps.can_scan}")
    for m in caps.messages:
        print(f"   - {m}")

    try:
        import uvicorn
        from api.app import create_app
        from api.config import Config
    except Exception as exc:
        print(f"\nERROR importando la aplicacion: {exc}")
        print("RESULTADO: ERROR (dependencias). Ejecuta setup.bat primero.")
        return 1

    cfg = Config.load()
    cfg.db_path = os.environ["LANMGR_DB_PATH"]
    cfg.auto_scan = False
    cfg.host = HOST
    cfg.port = PORT

    try:
        app = create_app(cfg)
    except Exception as exc:
        print(f"\nERROR construyendo la app: {exc}")
        import traceback
        traceback.print_exc()
        print("RESULTADO: ERROR")
        return 1

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    # Esperar a que el servidor este listo
    ready = False
    for _ in range(60):
        st, _ = req("/api/status", timeout=2)
        if st == 200:
            ready = True
            break
        time.sleep(0.5)
    if not ready:
        print("\nERROR: el servidor no respondio a tiempo.")
        print("RESULTADO: ERROR")
        server.should_exit = True
        return 1

    ok = True
    st, body = req("/api/status"); ok &= (st == 200)
    s = json.loads(body)
    print(f"\n[/api/status]   {st}  oui={s['oui_prefixes']} fase={s['phase']} auth={s['config']['auth_enabled']}")
    st, body = req("/"); ok &= (st == 200)
    print(f"[dashboard /]   {st}  {len(body)} bytes")
    st, _ = req("/styles.css"); ok &= (st == 200); print(f"[styles.css]    {st}")
    st, _ = req("/app.js"); ok &= (st == 200); print(f"[app.js]        {st}")

    print("\nEjecutando un escaneo REAL de la LAN ...")
    st, body = req("/api/network/scan", timeout=40)
    print(f"[/api/network/scan] {st}")
    try:
        scan = json.loads(body)
    except Exception:
        scan = {}
    if scan.get("error"):
        print(f"   escaneo con error controlado: {scan['error']}")
    else:
        for sub in scan.get("scanned_subnets", []):
            print(f"   subred: {sub.get('cidr')}  iface={sub.get('iface')}  gw={sub.get('gateway')}")
        print(f"   en linea: {scan.get('online_count')}  nuevos: {len(scan.get('new', []))}")

    st, body = req("/api/devices"); ok &= (st == 200)
    devs = json.loads(body)
    print(f"\n[/api/devices]  {st}  ->  {len(devs)} dispositivo(s)")
    if devs:
        print(f"   {'IP':<16}{'MAC':<19}{'Fabricante':<26}{'Tipo':<20}")
        print("   " + "-" * 78)
        for d in devs[:30]:
            print(f"   {str(d.get('ip') or '-'):<16}{d['mac']:<19}"
                  f"{str(d.get('vendor') or 'Desconocido')[:24]:<26}"
                  f"{str(d.get('device_type') or '')[:18]:<20}")

    # Endpoints de control activo: deben responder 501 (Fase 2/3), no simular nada
    st, _ = req("/api/devices/1/block", method="POST")
    print(f"\n[block  -> 501] {st}  (control activo = Fase 2)")
    st, _ = req("/api/network/speedtest")
    print(f"[speedtest -> 501] {st}  (test de velocidad = Fase 3)")

    # Apagar el servidor limpiamente
    server.should_exit = True
    time.sleep(1.0)

    print("\n" + "=" * 72)
    print("RESULTADO:", "OK - servidor levantado y verificado en Windows" if ok else "CON ERRORES")
    if not caps.can_scan:
        print("Nota: en esta corrida NO se pudo escanear (falta Npcap y/o admin).")
        print("      La API, el dashboard, la BD y la deteccion de requisitos funcionan.")
        print("      Para ver dispositivos reales: instala Npcap y ejecuta como administrador.")
    else:
        print("Escaneo real ejecutado: los dispositivos de arriba son de tu LAN.")
    print("=" * 72)

    # limpiar BD temporal
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(_tmp_db) + suffix)
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
