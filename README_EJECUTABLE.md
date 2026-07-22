# AdministradorLAN.exe — Guía rápida (una página)

**Qué es:** un único archivo `.exe` que levanta el **Administrador de Conexiones LAN** (un panel web para ver los dispositivos de tu red) **sin necesidad de instalar Python ni nada**. Doble clic y listo.

---

## Qué te va a pedir al abrirlo (y por qué)

1. **Permiso de administrador (ventana azul de Windows / UAC).**
   Escanear la red en Windows requiere privilegios elevados y un driver de captura. Por eso el programa pide elevación automáticamente al abrir. Es normal y esperable: hacé clic en **“Sí”**.

2. **Instalar Npcap, solo si falta (una vez).**
   Npcap es el **driver oficial de captura de red** de Windows — el mismo que usa Wireshark. Si no está instalado, el programa lo **descarga del sitio oficial `npcap.com`** y abre su instalador. Seguí los **2–3 pasos** del instalador de Npcap y **dejá marcada la opción “Install Npcap in WinPcap API-compatible Mode”**. El programa continúa solo cuando termina.
   *No hay “instalación silenciosa” para la versión gratuita de Npcap: esos 2–3 clics los tenés que dar vos, por diseño del propio Npcap.*

---

## Qué hace, en orden, al abrirlo

1. Verifica si Npcap está instalado. Si falta, te guía para instalarlo (punto 2 de arriba).
2. Levanta el servidor local.
3. **Abre el navegador automáticamente** en `http://localhost:8080`.
4. Deja un **ícono en la bandeja del sistema** (junto al reloj) con dos opciones: **“Abrir dashboard”** y **“Salir”**. Así no dependés de ninguna ventana de consola.

Para **cerrar** el programa: ícono de la bandeja → **Salir**.

---

## Cosas que conviene saber

- **El antivirus puede advertir** sobre un ejecutable nuevo. Es un **falso positivo común** de los `.exe` creados con PyInstaller (no está firmado con un certificado comercial). El archivo es seguro; si Windows SmartScreen lo bloquea, elegí **“Más información” → “Ejecutar de todas formas”**.
- **Datos y registros** quedan en dos carpetas **junto al `.exe`**: `data\` (la base de datos) y `logs\` (registros `app.log`, `launcher.log`, `audit.log`). Podés borrarlas sin problema; se recrean.
- **Acceso desde el celular u otra PC** de la misma red: por defecto el panel es solo local (`localhost`) por seguridad, porque la Fase 1 todavía no tiene login. La opción de exponerlo a toda la red llega con la autenticación (Fase 3).
- **Uso responsable:** esta herramienta es para **tu propia red** (o una que administres con autorización).

---

*Si algo no arranca, mirá `logs\app.log` en la carpeta del `.exe` y avisá.*
