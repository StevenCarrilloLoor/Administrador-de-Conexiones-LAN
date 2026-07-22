@echo off
rem ===================================================================
rem  Inicia el servidor (API + WebSocket + dashboard) en localhost:8080
rem  Para ESCANEAR la red se requiere Npcap + ejecutar como administrador:
rem  clic derecho en este archivo -> "Ejecutar como administrador".
rem ===================================================================
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo No existe el entorno virtual. Ejecuta primero setup.bat
  pause
  goto :eof
)
call ".venv\Scripts\activate.bat"
echo.
echo   Dashboard:  http://localhost:8080/
echo   API:        http://localhost:8080/api/status
echo   (Ctrl+C para detener)
echo.
echo   Para escanear la red: Npcap instalado + ejecutar como administrador.
echo.
python main.py
