@echo off
REM Actualizacion del panel en PC de sucursal (Windows).
REM Hace git pull si hay repo, reinstala deps Python y recompila el frontend.
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "REPO=%CD%"
set "BACKEND=%REPO%\backend"
set "FRONTEND=%REPO%\frontend"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "VENV_PIP=%BACKEND%\.venv\Scripts\pip.exe"

title Santander - Actualizacion
echo ========================================
echo  Actualizacion Control de Accesos
echo  Repo: %REPO%
echo ========================================
echo.

if not exist "%VENV_PY%" (
  echo ERROR: No hay venv. Ejecuta primero deploy\windows\1_instalar.bat
  pause
  exit /b 1
)

REM --- Desbloqueo de reglas + git pull (integrado) ---
REM Backup de config de sucursal, libera tracked locales que bloquean el merge,
REM hace pull y restaura las reglas de esta PC (no la plantilla del repo).
set "DATA=%BACKEND%\data"
set "BACKUP=%DATA%\_update_backup"
if not exist "%DATA%" mkdir "%DATA%"
if not exist "%BACKUP%" mkdir "%BACKUP%"

echo == Backup reglas de sucursal
if exist "%DATA%\panel_rules.json" (
  copy /y "%DATA%\panel_rules.json" "%BACKUP%\panel_rules.json" >nul
  echo    panel_rules.json
)
if exist "%DATA%\zaguan_device_target.json" (
  copy /y "%DATA%\zaguan_device_target.json" "%BACKUP%\zaguan_device_target.json" >nul
  echo    zaguan_device_target.json
)

where git >nul 2>&1
if errorlevel 1 (
  echo AVISO: Git no esta en PATH — actualiza el codigo a mano y vuelve a ejecutar.
  goto :after_git
)
if not exist "%REPO%\.git" (
  echo AVISO: No hay carpeta .git — actualiza el codigo a mano y vuelve a ejecutar.
  goto :after_git
)

echo == Liberando reglas tracked para permitir git pull
git checkout -- "backend/data/panel_rules.json" 2>nul
git checkout -- "backend/data/zaguan_device_target.json" 2>nul
git restore -- "backend/data/panel_rules.json" 2>nul
git restore -- "backend/data/zaguan_device_target.json" 2>nul

echo == git pull
git pull
if errorlevel 1 (
  echo.
  echo ERROR: git pull fallo.
  echo   Copia de seguridad en: backend\data\_update_backup\
  echo   Revisa el mensaje de git arriba y vuelve a lanzar este script.
  echo.
  pause
  exit /b 1
)

:after_git
echo == Restaurando reglas de esta sucursal
if exist "%BACKUP%\panel_rules.json" (
  copy /y "%BACKUP%\panel_rules.json" "%DATA%\panel_rules.json" >nul
  echo    panel_rules.json OK
) else (
  echo    ^(sin backup de panel_rules.json^)
)
if exist "%BACKUP%\zaguan_device_target.json" (
  copy /y "%BACKUP%\zaguan_device_target.json" "%DATA%\zaguan_device_target.json" >nul
  echo    zaguan_device_target.json OK
) else (
  echo    ^(sin backup de zaguan_device_target.json^)
)
echo.

echo.
echo == Dependencias Python
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PIP%" install -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto :fail

echo.
echo == Build del panel web
cd /d "%FRONTEND%"
if exist "package-lock.json" (
  call npm ci
) else (
  call npm install
)
if errorlevel 1 goto :fail
call npm run build
if errorlevel 1 goto :fail
cd /d "%REPO%"

echo.
echo ========================================
echo  Actualizacion completada
echo ========================================
echo  Reinicia el panel para cargar el codigo nuevo:
echo    1^) Cierra la ventana de 2_arrancar.bat si esta abierta
echo    2^) Ejecuta deploy\windows\2_arrancar.bat
echo.
set /p RESTART=Arrancar el panel ahora? [S/N]: 
if /i "%RESTART%"=="S" (
  start "Santander Panel" "%~dp02_arrancar.bat"
)
exit /b 0

:fail
echo.
echo ERROR en la actualizacion.
pause
exit /b 1
