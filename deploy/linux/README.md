# Panel de la sucursal en Linux (Ubuntu/Debian)

El backend (FastAPI + Modbus + CSIP + cliente SRC) no tiene dependencias de Windows: se ejecuta
igual en Linux. Esta carpeta lo instala como servicio `systemd`.

## Instalación

```bash
git clone <repo> ~/santander && cd ~/santander
sudo ./deploy/linux/install.sh <usuario>
```

El script:

- instala Python 3 (venv) y Node/npm, crea `backend/.venv` e instala `requirements.txt`;
- compila el panel web (`frontend/dist`, lo sirve el propio backend en `:8000`);
- añade el usuario al grupo `dialout` (acceso al adaptador USB RS-485);
- crea `backend/.env` desde `.env.example` si no existe;
- instala y arranca `santander-panel.service` (`Restart=always`) y abre 8000/8443 si `ufw` está activo.

Comandos útiles:

```bash
systemctl status santander-panel
journalctl -u santander-panel -f
sudo systemctl restart santander-panel
```

## Migrar una sucursal desde Windows

1. Parar el backend en el PC Windows.
2. Copiar al equipo Linux, en la misma ruta del repo:
   - `backend/.env`
   - `backend/data/` completo (`control_accesos.db`, `panel_rules.json`, `tls/`, …).
3. En `backend/.env` cambiar el puerto serie:
   - `MODBUS_SERIAL_PORT=/dev/serial/by-id/usb-…` (nombre estable; `ls /dev/serial/by-id/`),
     o `/dev/ttyUSB0` si solo hay un adaptador.
   - Si `TLS_CERT_FILE` / `TLS_KEY_FILE` tienen rutas de Windows, dejarlas como `./data/tls/server.crt` y `./data/tls/server.key`.
4. Si cambia la IP del panel: emitir de nuevo el certificado
   (`.venv/bin/python scripts/tls_ca.py issue --ip <IP>`) y actualizar la IP en tablets, ESP32 y Panphone (webhook CSIP).
5. `sudo systemctl restart santander-panel` y comprobar en el panel que las placas I/O aparecen conectadas.

## Actualizaciones desde el SRC

Al aplicar una actualización del panel publicada por el SRC, el backend copia el código nuevo y sale
del proceso; `systemd` lo relanza en ~3 s. Este reinicio automático solo se hace cuando el proceso corre
bajo `systemd`; para forzarlo o desactivarlo: `PANEL_RESTART_AFTER_UPDATE=true|false` en `.env`.

## Punto abierto: puente de audio/vídeo DVR (Release_vcx_x64)

El puente `audio_bridge.py` (`santander-app/Release_vcx_x64`) usa las DLL del SDK del DVR y el
Visual C++ Redistributable, por lo que **solo funciona en Windows**. Solo lo necesitan las puertas con
`intercomMode = bridge`; las que usan Panphone por SIP (`intercomMode = sip`) no dependen de él.

Opciones pendientes de decidir:

- mantener un equipo Windows (o VM) solo para el puente, apuntando las tablets a su `bridgeUrl`;
- conseguir la versión Linux del SDK del fabricante (`.so`) y portar el puente;
- prescindir del puente si todas las puertas pasan a SIP/Panphone y vídeo RTSP/HLS.
