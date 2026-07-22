@echo off
rem ===================================================================
rem  Descubrimiento por consola (Entregable Fase 1 #2)
rem  Escanea la LAN, imprime el inventario y lo guarda en la BD.
rem  Salida en logs\discovery.log
rem  NOTA: para escanear de verdad necesitas Npcap instalado y, en la
rem  mayoria de los casos, ejecutar como administrador.
rem ===================================================================
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist ".venv\Scripts\activate.bat" (
  echo No existe el entorno virtual. Ejecuta primero setup.bat
  goto :eof
)
call ".venv\Scripts\activate.bat"
python -m agent.cli --timeout 3 > "logs\discovery.log" 2>&1
type "logs\discovery.log"
echo.
echo (Salida guardada en logs\discovery.log)
