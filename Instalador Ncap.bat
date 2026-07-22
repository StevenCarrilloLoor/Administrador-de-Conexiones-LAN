@echo off
setlocal EnableDelayedExpansion
title Instalador de Npcap - Administrador de Conexiones LAN

echo ============================================
echo   Verificando si Npcap ya esta instalado...
echo ============================================
echo.

sc query npcap >nul 2>&1
if %errorlevel%==0 (
    echo Npcap ya esta instalado en este equipo. No hay nada mas que hacer.
    echo.
    pause
    exit /b 0
)

echo Npcap no fue encontrado en este equipo.
echo Descargando el instalador oficial desde npcap.com...
echo.

set "NPCAP_URL=https://npcap.com/dist/npcap-1.88.exe"
set "NPCAP_INSTALLER=%TEMP%\npcap-installer.exe"

powershell -NoProfile -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest -Uri '%NPCAP_URL%' -OutFile '%NPCAP_INSTALLER%' -UseBasicParsing } catch { exit 1 }"

if not exist "%NPCAP_INSTALLER%" (
    echo.
    echo No se pudo descargar el instalador automaticamente.
    echo Revisa tu conexion a internet, o descargalo manualmente desde:
    echo https://npcap.com/#download
    echo.
    pause
    exit /b 1
)

echo.
echo Descarga completa. Abriendo el instalador oficial de Npcap...
echo.
echo IMPORTANTE:
echo  - Windows puede mostrar una advertencia de SmartScreen porque es un
echo    archivo recien descargado. Es normal viniendo del sitio oficial;
echo    elegi "Mas info" y luego "Ejecutar de todas formas".
echo  - Windows tambien va a pedir permiso de administrador para instalar
echo    el driver. Acepta para continuar.
echo  - Segui los pasos en pantalla del instalador (Next, Next, Install).
echo.
pause

start /wait "" "%NPCAP_INSTALLER%"

echo.
echo Instalacion de Npcap finalizada.
del "%NPCAP_INSTALLER%" >nul 2>&1

echo.
echo Listo. Ya podes ejecutar el Administrador de Conexiones LAN.
pause