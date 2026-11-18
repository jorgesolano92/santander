@echo off
REM Quita el arranque automatico del panel.
setlocal EnableExtensions
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Santander-Control-Accesos.lnk"

if exist "%LINK%" (
  del /f /q "%LINK%"
  echo Eliminado: %LINK%
) else (
  echo No habia acceso directo de inicio.
)
pause
exit /b 0
