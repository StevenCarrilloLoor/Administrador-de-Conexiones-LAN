@echo off
rem ===================================================================
rem  Inicia el servidor accesible desde TODA la LAN (host 0.0.0.0),
rem  para entrar desde el celular/laptop a http://IP-DE-ESTA-PC:8080
rem
rem  ADVERTENCIA: en la Fase 1 el dashboard NO tiene autenticacion
rem  (la autenticacion es de la Fase 3). Exponerlo en la LAN implica
rem  que cualquiera en la red puede verlo. Usalo bajo tu criterio.
rem ===================================================================
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
  echo No existe el entorno virtual. Ejecuta primero setup.bat
  pause
  goto :eof
)
call ".venv\Scripts\activate.bat"
echo.
echo   ADVERTENCIA: exponiendo el dashboard en toda la LAN SIN autenticacion.
echo   La autenticacion llega en la Fase 3.
echo.
echo   Averigua la IP de esta PC con:  ipconfig
echo   Luego entra desde otro dispositivo a:  http://IP-DE-ESTA-PC:8080/
echo.
python main.py --host 0.0.0.0
