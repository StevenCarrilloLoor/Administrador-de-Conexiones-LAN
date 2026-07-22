@echo off
rem ===================================================================
rem  Verificacion end-to-end en Windows (sin abrir puertos).
rem  Ejercita API + dashboard + escaneo real y guarda logs\verify.log
rem  Para ver dispositivos reales: ejecutar como administrador con Npcap.
rem ===================================================================
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist ".venv\Scripts\activate.bat" (
  echo No existe el entorno virtual. Ejecuta primero setup.bat
  goto :eof
)
call ".venv\Scripts\activate.bat"
python tools\verify_windows.py > "logs\verify.log" 2>&1
type "logs\verify.log"
echo.
echo (Reporte guardado en logs\verify.log)
