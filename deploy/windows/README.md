# Panel de la sucursal en Windows

Scripts para el PC industrial de puerta / zaguán (Control de Accesos Banco Santander).

## Orden de ejecución

| # | Archivo | Cuándo |
|---|---------|--------|
| **1** | `1_instalar.bat` | **Primera vez** en el PC: venv, deps, build del panel, registro en inicio |
| **2** | `2_arrancar.bat` | Arrancar el software (manual o al encender el PC) |
| **3** | `3_actualizar.bat` | Cuando haya una versión nueva (`git pull` + rebuild) |
| **4** | `4_registrar-inicio.bat` | Solo si hace falta volver a registrar el arranque automático |
| **5** | `5_quitar-inicio.bat` | Quitar el arranque automático |

En una instalación nueva basta con ejecutar **1** y luego **2** (o aceptar el prompt de arranque al final de **1**).

## Requisitos

- Windows 10/11
- Python 3.11+ en PATH (`python --version`)
- Node.js LTS en PATH (`npm --version`)
- Git (recomendado, para `3_actualizar.bat`)

## Instalación

```bat
deploy\windows\1_instalar.bat
```

Luego revisa `backend\.env` (COM/RS-485, JWT, CSIP, Panphone, TLS).

## Arranque al encender

`1_instalar.bat` ya llama a `4_registrar-inicio.bat`. Eso crea:

`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Santander-Control-Accesos.lnk`

→ apunta a `2_arrancar.bat`. Al iniciar sesión de Windows se abre el panel.

## Actualizar

```bat
deploy\windows\3_actualizar.bat
```

Cierra la ventana del servicio anterior y vuelve a arrancar con `2_arrancar.bat` (o acepta el prompt del script).

## Notas

- El panel se sirve en `:8000` (y `:8443` si hay certificados TLS) desde `frontend/dist`.
- `BACKEND_RELOAD=0` en `2_arrancar.bat` evita el reinicio en caliente de desarrollo.
- Equivalente Linux: `deploy/linux/install.sh` + systemd.
