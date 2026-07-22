@echo off
rem ===================================================================
rem  Compila AdministradorLAN.exe (onefile) con PyInstaller.
rem  Genera DOS ejecutables en dist\:
rem    - AdministradorLAN-test.exe : consola, sin elevacion (verificacion)
rem    - AdministradorLAN.exe       : windowed + requireAdministrator (entrega)
rem  Salida detallada en logs\build.log
rem  Requiere haber corrido setup.bat antes (entorno .venv con las deps de la app).
rem ===================================================================
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs
set "LOG=%~dp0logs\build.log"
echo ===================================================== > "%LOG%"
echo  Build AdministradorLAN  %date% %time%                >> "%LOG%"
echo ===================================================== >> "%LOG%"

if not exist ".venv\Scripts\activate.bat" (
  echo No existe .venv. Ejecuta primero setup.bat
  echo No existe .venv. Ejecuta primero setup.bat >> "%LOG%"
  goto :end
)
call ".venv\Scripts\activate.bat"

echo Instalando dependencias de empaquetado (PyInstaller, pystray, Pillow)...
python -m pip install -r requirements-build.txt >> "%LOG%" 2>&1

echo Limpiando compilaciones anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [1/2] Compilando variante de prueba (consola, sin elevacion)...
set ACL_BUILD_TEST=1
python -m PyInstaller --noconfirm --clean AdministradorLAN.spec >> "%LOG%" 2>&1
set ACL_BUILD_TEST=

echo [2/2] Compilando ejecutable final (windowed, requireAdministrator)...
python -m PyInstaller --noconfirm --clean AdministradorLAN.spec >> "%LOG%" 2>&1

echo. >> "%LOG%"
echo --- Contenido de dist\ --- >> "%LOG%"
dir dist >> "%LOG%" 2>&1
if exist "dist\AdministradorLAN.exe" (
  echo RESULTADO: OK - dist\AdministradorLAN.exe generado. >> "%LOG%"
) else (
  echo RESULTADO: ERROR - no se genero el ejecutable. Revisa el log. >> "%LOG%"
)

:end
type "%LOG%"
echo.
echo (Log completo en logs\build.log)
endlocal
