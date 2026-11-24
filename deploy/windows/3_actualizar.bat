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

REM Preservar config de sucursal (reglas / zaguán) ante git pull.
REM Esos JSON ya no se versionan; en PCs viejos aun estan tracked y bloquean el pull.
set "DATA=%BACKEND%\data"
set "BACKUP=%DATA%\_update_backup"
if exist "%DATA%" (
  if not exist "%BACKUP%" mkdir "%BACKUP%"
  if exist "%DATA%\panel_rules.json" copy /y "%DATA%\panel_rules.json" "%BACKUP%\panel_rules.json" >nul
  if exist "%DATA%\zaguan_device_target.json" copy /y "%DATA%\zaguan_device_target.json" "%BACKUP%\zaguan_device_target.json" >nul
)

where git >nul 2>&1
if not errorlevel 1 (
  if exist "%REPO%\.git" (
    echo == Liberando reglas locales para permitir git pull
    git checkout -- "backend/data/panel_rules.json" 2>nul
    git checkout -- "backend/data/zaguan_device_target.json" 2>nul
    git restore -- "backend/data/panel_rules.json" 2>nul
    git restore -- "backend/data/zaguan_device_target.json" 2>nul
    echo == git pull
    git pull
    if errorlevel 1 (
      echo.
      echo ERROR: git pull fallo. Si sigue por panel_rules.json / zaguan_device_target.json:
      echo   1^) Ya hay copia en backend\data\_update_backup\
      echo   2^) Ejecuta:
      echo      git checkout -- backend/data/panel_rules.json backend/data/zaguan_device_target.json
      echo      git pull
      echo   3^) Restaura desde _update_backup y vuelve a lanzar este script.
      echo.
      pause
      exit /b 1
    )
  ) else (
    echo AVISO: No hay carpeta .git — actualiza el codigo a mano y vuelve a ejecutar.
  )
) else (
  echo AVISO: Git no esta en PATH — actualiza el codigo a mano y vuelve a ejecutar.
)

REM Restaurar SIEMPRE la config de esta sucursal (no la plantilla del repo)
if exist "%BACKUP%\panel_rules.json" (
  copy /y "%BACKUP%\panel_rules.json" "%DATA%\panel_rules.json" >nul
  echo == Conservada panel_rules.json de esta sucursal
)
if exist "%BACKUP%\zaguan_device_target.json" (
  copy /y "%BACKUP%\zaguan_device_target.json" "%DATA%\zaguan_device_target.json" >nul
  echo == Conservada zaguan_device_target.json de esta sucursal
)

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
