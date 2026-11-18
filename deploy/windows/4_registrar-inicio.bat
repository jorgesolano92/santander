@echo off
REM Registra 2_arrancar.bat en el inicio de sesion de Windows (carpeta Startup).
setlocal EnableExtensions
cd /d "%~dp0"

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\Santander-Control-Accesos.lnk"
set "TARGET=%~dp02_arrancar.bat"

if not exist "%STARTUP%" (
  echo ERROR: No se encuentra la carpeta Startup del usuario.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%LINK%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 1; $s.Description = 'Control de Accesos Santander'; $s.Save()"

if errorlevel 1 (
  echo ERROR: No se pudo crear el acceso directo.
  pause
  exit /b 1
)

echo Listo. Al iniciar sesion se lanzara:
echo   %TARGET%
echo Acceso directo:
echo   %LINK%
echo.
echo Para quitarlo: deploy\windows\5_quitar-inicio.bat
if /i not "%~1"=="/nopause" pause
exit /b 0
