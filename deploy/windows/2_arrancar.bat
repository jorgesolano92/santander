@echo off
REM Arranque del panel Control de Accesos (Banco Santander / SAIMA).
REM Pensado para inicio de Windows y uso manual en el PC de la sucursal.
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "REPO=%CD%"
set "BACKEND=%REPO%\backend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "BACKEND_RELOAD=0"

title Santander - Control de Accesos
echo ========================================
echo  Control de Accesos - arranque
echo  Repo: %REPO%
echo ========================================
echo.

if not exist "%VENV_PY%" (
  echo ERROR: No existe el entorno Python:
  echo   %VENV_PY%
  echo Ejecuta primero: deploy\windows\1_instalar.bat
  pause
  exit /b 1
)

if not exist "%BACKEND%\.env" (
  echo AVISO: No hay backend\.env — el servicio puede fallar o usar defaults.
  echo Copia backend\.env.example a backend\.env y revisa COM / secretos / CSIP.
  echo.
)

if not exist "%REPO%\frontend\dist\index.html" (
  echo AVISO: No hay build del panel ^(frontend\dist^).
  echo Ejecuta 1_instalar.bat o 3_actualizar.bat para compilarlo.
  echo.
)

cd /d "%BACKEND%"
echo Arrancando panel en http://0.0.0.0:8000 ...
echo ^(HTTPS/WSS :8443 si hay certificados TLS^)
echo Cierra esta ventana solo para detener el servicio.
echo.
"%VENV_PY%" run.py
set "EC=%ERRORLEVEL%"
echo.
echo El proceso termino con codigo %EC%.
pause
exit /b %EC%
