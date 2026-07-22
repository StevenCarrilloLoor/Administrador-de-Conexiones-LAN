"""Punto de entrada del Administrador de Conexiones LAN.

Arranca el servidor FastAPI (API + WebSocket + dashboard) con Uvicorn.

Uso:
    python main.py                     # usa config.ini / valores por defecto
    python main.py --host 0.0.0.0      # exponer en la LAN (requiere auth: Fase 3)
    python main.py --port 9000
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Asegurar que la raiz del proyecto este en sys.path (agent/, api/, db/)
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Administrador de Conexiones LAN")
    parser.add_argument("--host", help="direccion de escucha (override)")
    parser.add_argument("--port", type=int, help="puerto (override)")
    args = parser.parse_args()

    if args.host:
        os.environ["LANMGR_HOST"] = args.host
    if args.port:
        os.environ["LANMGR_PORT"] = str(args.port)

    import uvicorn

    from agent.platform_checks import check_capabilities
    from api.config import Config

    cfg = Config.load()
    caps = check_capabilities()

    print("=" * 70)
    print("  Administrador de Conexiones LAN — Fase 1")
    print("=" * 70)
    print(f"  Dashboard:  http://{'localhost' if not cfg.exposed_on_lan else cfg.host}:{cfg.port}/")
    print(f"  API:        http://{'localhost' if not cfg.exposed_on_lan else cfg.host}:{cfg.port}/api/status")
    print(f"  Admin: {'SI' if caps.is_admin else 'NO'}   Npcap: {'SI' if caps.npcap else 'NO'}"
          f"   Puede escanear: {'SI' if caps.can_scan else 'NO'}")
    if not caps.can_scan:
        print("  ! Requisitos incompletos — el escaneo no arrancara hasta corregirlos:")
        for m in caps.messages:
            print(f"    - {m}")
    if cfg.exposed_on_lan:
        print("  ! Expuesto en la LAN SIN autenticacion (auth = Fase 3). Ten cuidado.")
    print("=" * 70)

    # Construye la app una sola vez (sin efectos secundarios al importar el modulo).
    from api.app import create_app
    app = create_app(cfg)
    uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
