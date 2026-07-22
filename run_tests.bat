@echo off
rem ===================================================================
rem  Corre la suite de tests (pytest) en el entorno .venv.
rem  Instala las dependencias de test si faltan. Salida en logs\tests.log
rem  Requiere haber corrido setup.bat antes.
rem ===================================================================
cd /d "%~dp0"
if not exist logs mkdir logs
if not exist ".venv\Scripts\activate.bat" (
  echo No existe .venv. Ejecuta primero setup.bat
  goto :eof
)
call ".venv\Scripts\activate.bat"
python -m pip install -q -r requirements-dev.txt
python -m pytest -q > "logs\tests.log" 2>&1
type "logs\tests.log"
echo.
echo (Resultado en logs\tests.log)
