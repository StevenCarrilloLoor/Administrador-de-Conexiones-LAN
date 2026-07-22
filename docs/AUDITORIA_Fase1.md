# Auditoría — Administrador de Conexiones LAN (Fase 1 + empaquetado)

**Fecha:** 2026-07-22
**Alcance auditado:** API, dashboard web, modelo de datos/BD, arquitectura general y el empaquetado (.exe).
**Fuera de alcance (acordado):** el motor de red de bajo nivel (escaneo ARP / futuro bloqueo / límite de ancho de banda) — lo revisa Opus.
**Método:** revisión de código archivo por archivo + un sub-agente revisor independiente; cada hallazgo verificado contra el código real (con archivo y línea).

> **Importante:** este documento es SOLO el listado de hallazgos. **No se aplicó ningún cambio** derivado de esta auditoría todavía. Vos aprobás qué se corrige y en qué orden; recién ahí se aplica y se entrega un changelog.
>
> Excepción ya resuelta (parte del armado del .exe, no de la auditoría): durante el build se detectó que **`db/schema.sql` no se empaquetaba** en el ejecutable, lo que hacía fallar `db.init()` en el .exe. Se corrigió para poder entregar un .exe funcional (resolución vía `apppaths` + inclusión en el `.spec`). Queda documentado acá por transparencia.

## Resumen

| Severidad | Cantidad |
|---|---|
| BUG (defecto real: incorrecto / crash / inconsistencia / riesgo de seguridad) | 6 |
| MEJORA (estilo / mantenibilidad / robustez, sin defecto funcional actual) | 11 |

Contexto: la Fase 1 corre por defecto en `127.0.0.1` y sin autenticación (la auth es Fase 3). Eso acota — pero no elimina — el impacto de los hallazgos de seguridad, porque el navegador del propio equipo sí alcanza `localhost`.

---

## BUGS (más severo primero)

### B1 · CORS comodín (`allow_origins=["*"]`) sin autenticación → fuga/mutación cross-origin
- **Archivo:** `api/app.py` (middleware CORS, ~línea 71-74)
- **Problema:** el dashboard se sirve del **mismo origen** que la API (`app.mount("/")`), así que CORS no es necesario. El comodín `*` (sin credenciales) permite que **cualquier web** que el usuario visite lea las respuestas de `http://localhost:8080` desde su navegador.
- **Escenario:** el usuario tiene la app abierta y entra a `evil.com`; ese sitio hace `fetch("http://localhost:8080/api/devices")` y **lee todo el inventario** (MAC, IP, hostname, grupos). Con `allow_methods:["*"]`, un `PATCH` cross-origin para renombrar/agrupar también pasa.
- **Corrección:** quitar el middleware CORS (es same-origin) o restringir a orígenes explícitos. Nunca `["*"]` en un servicio local sin auth.
- **Esfuerzo:** S

### B2 · `GET /api/network/scan` tiene efectos secundarios (escribe en la BD)
- **Archivo:** `api/routers/network.py` (~línea 9-14)
- **Problema:** `scan_once()` hace `upsert` de dispositivos e inserta eventos y alertas. Exponer una operación mutante como `GET` viola REST y la vuelve disparable por un `GET` "simple" cross-site (un `<img src=".../api/network/scan">`, un prefetch del navegador o un crawler) sin que el usuario lo sepa, incluso sin depender de B1.
- **Escenario:** cualquier página con `<img src="http://localhost:8080/api/network/scan">` lanza un escaneo y escribe en la BD del usuario.
- **Corrección:** cambiar a `POST` (y sumar protección CSRF cuando llegue la auth de Fase 3). Ajustar el `fetch` del dashboard (`app.js`).
- **Esfuerzo:** S

### B3 · `create_app`→`setup_logging` borra el handler de `launcher.log` (diagnóstico del launcher se pierde)
- **Archivos:** `api/logging_setup.py` (`root.handlers.clear()`) vs. `launcher.py` (`setup_launcher_logging`); **confirmado empíricamente:** tras correr el .exe, `logs/launcher.log` quedó en **0 bytes**.
- **Problema:** el launcher agrega un handler a `launcher.log` sobre el logger `"lanmanager"`; luego `create_app()` llama `setup_logging()` que hace `handlers.clear()` sobre ese mismo logger y lo elimina. Los mensajes posteriores del launcher (incluida la traza de un error fatal) van a `app.log`, aunque los diálogos de error dicen "revisá `launcher.log`".
- **Escenario:** si el servidor falla tras `create_app`, el usuario abre `launcher.log` (vacío) en vez de `app.log`.
- **Corrección:** no usar `handlers.clear()` indiscriminado, o que el launcher use un logger propio con `propagate=False` y su handler.
- **Esfuerzo:** S

### B4 · Cancelar/abandonar la instalación de Npcap congela el arranque hasta 15 minutos
- **Archivos:** `launcher.py` (`ensure_npcap()` corre antes de `start_server()`), `agent/npcap_bootstrap.py` (`launch_installer_and_wait`, `wait_timeout=900`)
- **Problema:** se lanza el instalador con `Popen` pero **se descarta el handle** y solo se sondea `npcap_installed()` durante 900 s. Si el usuario **cancela** el instalador, el bucle corre los 15 minutos completos y el servidor no arranca en ese tiempo → la app parece colgada.
- **Escenario:** abrir el .exe → aceptar descargar Npcap → cancelar el instalador → 15 min sin dashboard.
- **Corrección:** guardar el proceso y romper el bucle si `proc.poll() is not None` (instalador cerrado); y/o arrancar el servidor en paralelo a la espera de Npcap; reducir el timeout.
- **Esfuerzo:** M

### B5 · `POST /api/rules` con `device_id` inexistente responde 500 (debería ser 4xx)
- **Archivos:** `api/routers/rules.py` (`create_rule`), `db/repositories.py` (`RuleRepository.add`), FK activas en `db/database.py`
- **Problema:** no se valida `device_id`; el `INSERT` con FK activadas lanza `IntegrityError` no capturado → **HTTP 500** ante entrada inválida del cliente. Tampoco se valida coherencia por tipo (p. ej. `bandwidth_limit` sin `limit_kbps`).
- **Escenario:** `{"rule_type":"block","device_id":999999}` → 500.
- **Corrección:** verificar existencia del dispositivo (404/422) y/o capturar `IntegrityError` y mapear a 4xx; validar campos por `rule_type`.
- **Esfuerzo:** S

### B6 · La gráfica "offline" no existe: falta `dashboard/vendor/chart.umd.min.js`
- **Archivos:** `dashboard/index.html` (loader que intenta `vendor/chart.umd.min.js` y cae al CDN), no está el archivo en el repo/bundle.
- **Problema:** la promesa de "primero local (offline)" no se cumple porque el archivo vendorizado no está incluido; la gráfica depende siempre de Internet (el `setup.bat` intenta descargarlo, pero no está garantizado). Degrada de forma controlada (muestra aviso), por eso es de severidad baja.
- **Corrección:** incluir `dashboard/vendor/chart.umd.min.js` en el repo y en `datas` del `.spec`, o quitar la promesa de offline.
- **Esfuerzo:** S

---

## MEJORAS (estilo / mantenibilidad / robustez)

### M1 · Sin migraciones de esquema (upgrades no aplican cambios a BD existentes)
- **Archivos:** `db/schema.sql`, `db/database.py` (`CREATE TABLE IF NOT EXISTS`)
- **Problema:** si en una versión futura se agrega/renombra una columna, las BD ya creadas no se actualizan (el `IF NOT EXISTS` no altera tablas existentes) y el código que espere la columna nueva fallará. No hay versionado de esquema.
- **Corrección:** tabla `schema_version` + migraciones incrementales idempotentes al iniciar.
- **Esfuerzo:** M

### M2 · Crecimiento no acotado de `connection_events` / `alerts`
- **Archivos:** `db/schema.sql`, `agent/scanner_service.py` (inserciones por escaneo)
- **Problema:** cada escaneo (por defecto 30 s) puede insertar eventos/alertas sin retención. Además, tras reiniciar, `_online_macs` arranca vacío y el primer escaneo registra `connected` para todos los presentes; con MAC aleatoria cada rotación crea fila+alerta nuevas. A largo plazo la BD crece sin techo.
- **Corrección:** retención por antigüedad + `VACUUM` periódico; considerar consolidar MAC aleatorias.
- **Esfuerzo:** M

### M3 · El instalador de Npcap se ejecuta (elevado) sin verificar firma ni hash
- **Archivo:** `agent/npcap_bootstrap.py` (`download_installer` + `Popen`)
- **Problema:** se descarga y ejecuta un `.exe` con privilegios de administrador confiando solo en HTTPS al dominio oficial. Defensa en profundidad razonable dado que corre elevado.
- **Corrección:** verificar la firma Authenticode del binario (o un SHA-256 fijado por versión) antes de ejecutarlo.
- **Esfuerzo:** M

### M4 · WebSocket ejecuta consulta SQLite bloqueante dentro del coroutine async
- **Archivo:** `api/app.py` (`ws_live`, mensaje `hello` llama `device_repo.all()`)
- **Problema:** una consulta SQLite síncrona en el hilo del event loop lo bloquea durante la lectura; con BD grande o muchos clientes degrada la responsividad.
- **Corrección:** `await run_in_threadpool(...)` o snapshot precomputado.
- **Esfuerzo:** S

### M5 · `StreamHandler` a `sys.stderr` (que puede ser `None`) en el .exe windowed
- **Archivos:** `api/logging_setup.py`, interactúa con `console=False` del `.spec`
- **Problema:** en el .exe final sin consola, `sys.stderr` suele ser `None`; el `StreamHandler` es inútil y genera errores internos de logging (suprimidos, pero ruido).
- **Corrección:** no añadir `StreamHandler` cuando `sys.stderr is None`.
- **Esfuerzo:** S

### M6 · Parámetro `limit` sin validar en `/api/alerts` (negativo → devuelve todo)
- **Archivos:** `api/routers/alerts.py`, `db/repositories.py` (`... LIMIT ?`)
- **Problema:** `GET /api/alerts?limit=-1` → en SQLite `LIMIT -1` = sin límite (respuesta no acotada); `limit=0` devuelve vacío.
- **Corrección:** `Query(default=100, ge=1, le=500)`.
- **Esfuerzo:** S

### M7 · Falta validación de longitud en `PATCH /api/devices/{id}` (nombre/grupo)
- **Archivos:** `api/models.py` (`DeviceUpdateIn`), `api/routers/devices.py`
- **Problema:** `custom_name`/`device_group` no tienen cota de longitud; se puede guardar texto arbitrariamente grande.
- **Corrección:** `Field(max_length=...)` en el modelo.
- **Esfuerzo:** S

### M8 · `POST /api/rules` relee todas las reglas para devolver la creada (y puede dar `TypeError`)
- **Archivo:** `api/routers/rules.py`
- **Problema:** `next((r for r in rule_repo.all() ...), None)` es O(n) y, si diera `None`, `_to_out(None)` → `dict(None)` → `TypeError` → 500.
- **Corrección:** agregar `RuleRepository.get(id)` o construir la salida desde el cuerpo + `rid`.
- **Esfuerzo:** S

### M9 · `/api/network/scan` sin `response_model`; `ScanResult` definido pero sin usar
- **Archivos:** `api/routers/network.py`, `api/models.py`
- **Problema:** la respuesta es un dict de forma variable (`skipped`/`error`/summary) no tipada; el frontend depende de claves no documentadas.
- **Corrección:** tipar la respuesta o documentar las formas; eliminar el modelo si no se usa.
- **Esfuerzo:** S

### M10 · Lista filtrada a vacío no muestra "sin resultados"
- **Archivo:** `dashboard/app.js` (`#empty-state` atado solo a `state.devices.length`)
- **Problema:** si hay dispositivos pero el filtro/búsqueda los excluye a todos, el área queda en blanco sin explicación.
- **Corrección:** mensaje "sin resultados para el filtro" cuando `shown.length === 0 && state.devices.length > 0`.
- **Esfuerzo:** S

### M11 · Detalles menores de empaquetado/arranque
- **`build.bat`:** el build final no usa `--clean` (reutiliza el `build\` de la variante de prueba con distinta config; frágil). → agregar `--clean`.
- **`host = 0.0.0.0`:** la URL abierta/impresa es `http://0.0.0.0:8080/`, poco fiable en navegadores. → usar `localhost` o la IP LAN real. (`api/config.py`, `main.py`, `launcher.py`)
- **`sys.path.insert` en `config.py`/`oui.py`/`database.py`:** funciona, pero acopla vía efecto de import; podría centralizarse.
- **Esfuerzo:** S

---

## Orden de aplicación sugerido (a tu criterio)

1. **Seguridad rápida (S):** B1 (quitar CORS), B2 (`scan` a POST). Bajan el riesgo con cambios chicos.
2. **Robustez del .exe (S/M):** B3 (logging del launcher), B4 (no congelar si se cancela Npcap), M5 (StreamHandler sin consola), M11 (`--clean`, URL `0.0.0.0`). Mejoran la experiencia de la entrega principal.
3. **Validación de API (S):** B5, M6, M7, M8, M9.
4. **UX/offline (S):** B6 (vendorizar Chart.js), M10 (mensaje de filtro vacío).
5. **Datos a futuro (M):** M1 (migraciones), M2 (retención), M3 (firma del instalador).

**Nada de lo anterior está aplicado.** Decime cuáles querés y en qué orden, y los implemento con su changelog.
