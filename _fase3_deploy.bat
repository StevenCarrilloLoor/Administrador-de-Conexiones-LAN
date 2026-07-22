@echo off
rem ============================================================
rem  Fase 3 - Despliegue automatico
rem  1) Instala dependencias (incluye bcrypt y requests)
rem  2) Corre la suite de tests (pytest)
rem  3) Si TODOS pasan, hace commit y push a GitHub (dispara CI)
rem  Log unico: logs\fase3_deploy_v1.log   (RESULTADO: al final)
rem ============================================================
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=%~dp0logs\fase3_deploy_v1.log"

if not exist ".venv\Scripts\activate.bat" (
  echo ERROR: no existe .venv. Corre setup.bat primero.> "%LOG%"
  echo RESULTADO: SIN_VENV>> "%LOG%"
  type "%LOG%"
  goto :fin
)
call ".venv\Scripts\activate.bat"

echo ==== 1) Instalando dependencias ==== > "%LOG%"
python -m pip install -q -r requirements.txt >> "%LOG%" 2>&1
python -m pip install -q -r requirements-dev.txt >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo ==== 2) Corriendo la suite de tests ==== >> "%LOG%"
python -m pytest -q >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
echo. >> "%LOG%"
echo PYTEST_EXIT=%RC% >> "%LOG%"

if not "%RC%"=="0" (
  echo RESULTADO: TESTS_FALLARON_NO_SE_SUBE >> "%LOG%"
  type "%LOG%"
  goto :fin
)

echo. >> "%LOG%"
echo ==== 3) Tests OK - staging de los 30 archivos de Fase 3 ==== >> "%LOG%"
git add AdministradorLAN.spec agent/scanner_service.py agent/arp_defense.py agent/notifier.py agent/speedtest.py agent/wol.py api/app.py api/auth.py api/config.py api/models.py api/routers/auth.py api/routers/devices.py api/routers/network.py api/routers/tools.py dashboard/app.js dashboard/index.html dashboard/login.html dashboard/styles.css db/database.py db/repositories.py requirements.txt tests/conftest.py tests/test_api.py tests/test_arp_defense.py tests/test_auth.py tests/test_database.py tests/test_notifier.py tests/test_scanner_service.py tests/test_tools.py tests/test_wol.py >> "%LOG%" 2>&1

git commit -m "Fase 3: autenticacion, reglas/horarios UI, notificaciones, WoL, speedtest, exportacion y defensa anti-spoofing; +43 tests" >> "%LOG%" 2>&1
echo COMMIT_EXIT=%ERRORLEVEL% >> "%LOG%"

echo. >> "%LOG%"
echo ==== 4) Subiendo a GitHub (origin main) ==== >> "%LOG%"
git push origin main >> "%LOG%" 2>&1
set "PRC=%ERRORLEVEL%"
echo GIT_PUSH_EXIT=%PRC% >> "%LOG%"
if "%PRC%"=="0" (
  echo RESULTADO: OK_TESTS_Y_PUSH >> "%LOG%"
) else (
  echo RESULTADO: TESTS_OK_PERO_PUSH_FALLO >> "%LOG%"
)

:fin
echo ---- FIN ---- >> "%LOG%"
type "%LOG%"
