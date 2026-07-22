# Changelog — correcciones de auditoría, tests y CI (Fase 1)

**Fecha:** 2026-07-22
**Commit:** `a4c4a83` — *"Fase 1: corrige 6 bugs, aplica 11 mejoras, agrega tests y CI"*
**Repo:** github.com/StevenCarrilloLoor/Administrador-de-Conexiones-LAN (rama `main`)

Se aplicaron **todos** los hallazgos del documento de auditoría (`docs/AUDITORIA_Fase1.md`), más una suite de tests y CI. Todo verificado con la suite en verde en el sandbox y en tu PC (Windows 11 / Python 3.13), y con un escaneo real que encontró **29 dispositivos** de tu red.

## Bugs corregidos

- **B1 — CORS comodín.** Se eliminó el middleware `CORSMiddleware` (`allow_origins=["*"]`). El dashboard es *same-origin*, así que no se necesita CORS; ahora ninguna web externa puede leer/modificar el inventario. *(api/app.py)*
- **B2 — `GET /api/network/scan` con efectos secundarios.** El escaneo pasó a **POST** (escribe en la BD). El dashboard ahora hace `POST`. *(api/routers/network.py, dashboard/app.js)*
- **B3 — Logging del launcher se perdía.** `setup_logging` ya no borra handlers ajenos (solo los propios, marcados); el launcher usa su logger `lanmanager.launcher`. `launcher.log` conserva su traza aunque el servidor arranque después. *(api/logging_setup.py, launcher.py)*
- **B4 — Cuelgue hasta 15 min si se cancela Npcap.** `launch_installer_and_wait` ahora detecta que el instalador se cerró (`proc.poll()`) y corta la espera enseguida. *(agent/npcap_bootstrap.py)*
- **B5 — `POST /api/rules` con `device_id` inexistente daba 500.** Se validan `device_id`, coherencia por tipo (`bandwidth_limit`→kbps, `schedule`→HH:MM) y se captura `IntegrityError` → respuestas 404/422. *(api/routers/rules.py)*
- **B6 — Chart.js "offline" no existía.** Se **vendorizó** `dashboard/vendor/chart.umd.min.js` (Chart.js 4.4.1, ~200 KB) en el repo y en el bundle del `.exe`. Ahora la gráfica funciona sin internet. *(dashboard/vendor/)*

## Mejoras aplicadas

- **M1 — Migraciones de esquema.** Versionado con `PRAGMA user_version`; `init()` aplica migraciones incrementales. *(db/database.py)*
- **M2 — Retención de historial.** Purga diaria de eventos y de alertas ya vistas más viejas que `retention_days` (30 por defecto) + `VACUUM`. *(db/repositories.py, agent/scanner_service.py, api/config.py)*
- **M3 — Firma del instalador de Npcap.** Se verifica la firma Authenticode (Get-AuthenticodeSignature, firmante Insecure.Com/Npcap) antes de ejecutarlo elevado. *(agent/npcap_bootstrap.py, launcher.py)*
- **M4 — WebSocket bloqueante.** La lectura SQLite del mensaje `hello` va a un threadpool (`run_in_threadpool`). *(api/app.py)*
- **M5 — `StreamHandler` sin consola.** No se agrega handler de consola cuando `sys.stderr` es `None` (el `.exe` windowed). *(api/logging_setup.py)*
- **M6 — `limit` de alertas sin validar.** `Query(ge=1, le=500)`. *(api/routers/alerts.py)*
- **M7 — Longitud de nombre/grupo.** `max_length` en `DeviceUpdateIn` (120/60). *(api/models.py)*
- **M8 — `RuleRepository.get`.** Se agrega `get(id)` y se usa al crear reglas (evita releer todo y un posible `TypeError`). *(db/repositories.py, api/routers/rules.py)*
- **M9 — `response_model` de scan.** `ScanResult` tipado (con `skipped`/`error`) aplicado al endpoint. *(api/models.py, api/routers/network.py)*
- **M10 — Filtro vacío sin mensaje.** El dashboard distingue "sin inventario" de "sin resultados para el filtro". *(dashboard/app.js)*
- **M11 — Detalles de empaquetado.** `--clean` en el build final; URL `0.0.0.0` se muestra/abre como `localhost`. *(build.bat, main.py, launcher.py)*

## Extra (descubierto en pruebas reales)

- **Capacidad de escaneo sin admin.** El escaneo ARP funciona con Npcap en modo compatible **sin** privilegios de administrador (verificado: 29 dispositivos). `can_scan` ya no exige admin; admin queda como requisito solo del **control activo** (Fase 2). El dashboard muestra un aviso ámbar en ese caso. *(agent/platform_checks.py, dashboard/app.js)*
- **`db/schema.sql` no se empaquetaba** en el `.exe` (bug solo visible congelado). Se resuelve vía `apppaths` y se incluye en el `.spec`. *(db/database.py, AdministradorLAN.spec, apppaths.py)*

## Tests y CI

- **Suite pytest (50 pruebas)** en `tests/`, con la red **mockeada** (no requiere Npcap ni LAN): repositorios/BD, migraciones, OUI, inferencia de tipo, servicio de escaneo (altas/bajas/cambios de IP), bootstrap de Npcap, `apppaths`, config y **API** (validaciones, 404/422, 501, POST scan, sin CORS, estáticos + Chart.js).
- **Resultado:** 50/50 en verde en el sandbox (Linux) y en tu PC (Windows 11 / Python 3.13).
- **CI:** `.github/workflows/tests.yml` corre `pytest` en **cada push y PR**, con Python 3.11, 3.12 y 3.13.

## Verificación real

Escaneo real en tu red (con Npcap): **29 dispositivos** detectados, con fabricante por OUI y tipo inferido — router Huawei, iPhone/Mac, Amazon Echo, 2 cámaras Hikvision, 4 dispositivos Tuya, AP TP-Link, etc.
