@echo off
REM Desbloquea git pull cuando hay cambios locales en reglas de sucursal.
REM Uso (en la PC de sucursal, como Administrador o normal):
REM   cd C:\SW\santander-main
REM   deploy\windows\desbloquear_pull_reglas.bat
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "DATA=%CD%\backend\data"
set "BACKUP=%DATA%\_update_backup"

echo ========================================
echo  Desbloquear pull ^(reglas de sucursal^)
echo  Repo: %CD%
echo ========================================
echo.

if not exist "%CD%\.git" (
  echo ERROR: No hay repositorio git aqui.
  pause
  exit /b 1
)

if not exist "%BACKUP%" mkdir "%BACKUP%"
if exist "%DATA%\panel_rules.json" (
  copy /y "%DATA%\panel_rules.json" "%BACKUP%\panel_rules.json" >nul
  echo Backup: panel_rules.json
)
if exist "%DATA%\zaguan_device_target.json" (
  copy /y "%DATA%\zaguan_device_target.json" "%BACKUP%\zaguan_device_target.json" >nul
  echo Backup: zaguan_device_target.json
)

echo Liberando archivos tracked...
git checkout -- "backend/data/panel_rules.json" 2>nul
git checkout -- "backend/data/zaguan_device_target.json" 2>nul

echo.
echo == git pull
git pull
if errorlevel 1 (
  echo ERROR: git pull sigue fallando. Revisa el mensaje de git.
  pause
  exit /b 1
)

if exist "%BACKUP%\panel_rules.json" (
  copy /y "%BACKUP%\panel_rules.json" "%DATA%\panel_rules.json" >nul
  echo Restaurado: panel_rules.json
)
if exist "%BACKUP%\zaguan_device_target.json" (
  copy /y "%BACKUP%\zaguan_device_target.json" "%DATA%\zaguan_device_target.json" >nul
  echo Restaurado: zaguan_device_target.json
)

echo.
echo Listo. Ya puedes ejecutar deploy\windows\3_actualizar.bat
echo  ^(o npm build / reiniciar el panel^).
pause
exit /b 0
