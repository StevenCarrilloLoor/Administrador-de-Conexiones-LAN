@echo off
rem ===================================================================
rem  Administrador de Conexiones LAN - Instalacion (Windows)
rem  Crea el entorno virtual .venv e instala las dependencias.
rem  La salida se guarda en logs\setup.log
rem ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=%~dp0logs\setup.log"

echo =====================================================>  "%LOG%"
echo  Setup - Administrador de Conexiones LAN            >> "%LOG%"
echo  %date% %time%                                      >> "%LOG%"
echo =====================================================>> "%LOG%"

echo Buscando Python 3...
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY ( python --version >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo ERROR: No se encontro Python 3. Instala Python 3.11+ desde https://www.python.org/downloads/ >> "%LOG%"
  echo RESULTADO: ERROR >> "%LOG%"
  echo ERROR: No se encontro Python 3. Instala Python 3.11+ y reintenta.
  goto :end
)
echo Python detectado: >> "%LOG%"
%PY% --version >> "%LOG%" 2>&1

if not exist ".venv" (
  echo Creando entorno virtual .venv ... >> "%LOG%"
  echo Creando entorno virtual .venv ...
  %PY% -m venv .venv >> "%LOG%" 2>&1
)
call ".venv\Scripts\activate.bat"

echo Actualizando pip ... >> "%LOG%"
python -m pip install --upgrade pip >> "%LOG%" 2>&1
echo Instalando dependencias (esto puede tardar unos minutos) ...
echo Instalando dependencias ... >> "%LOG%"
python -m pip install -r requirements.txt >> "%LOG%" 2>&1
set "PIPRC=%ERRORLEVEL%"

rem --- Chart.js para uso offline (opcional, no critico) ---
if not exist "dashboard\vendor" mkdir "dashboard\vendor"
if not exist "dashboard\vendor\chart.umd.min.js" (
  echo Descargando Chart.js para uso offline (opcional) ... >> "%LOG%"
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js' -OutFile 'dashboard\vendor\chart.umd.min.js'; Write-Output 'Chart.js OK'}catch{Write-Output ('Chart.js omitido (se usara CDN): ' + $_.Exception.Message)}" >> "%LOG%" 2>&1
)

echo. >> "%LOG%"
if "%PIPRC%"=="0" (
  echo RESULTADO: OK - dependencias instaladas correctamente. >> "%LOG%"
  echo.
  echo Instalacion COMPLETADA. Ahora ejecuta run_server.bat ^(como administrador para escanear^).
) else (
  echo RESULTADO: ERROR - fallo la instalacion de dependencias ^(codigo %PIPRC%^). >> "%LOG%"
  echo.
  echo La instalacion FALLO. Revisa logs\setup.log
)

:end
echo Log completo en: %LOG%
endlocal
