@echo off
REM Instalacion en PC de sucursal (Windows) - Control de Accesos Banco Santander.
REM Requisitos: Python 3.11+ en PATH, Node.js/npm en PATH, (opcional) Git.
setlocal EnableExtensions
cd /d "%~dp0..\.."

set "REPO=%CD%"
set "BACKEND=%REPO%\backend"
set "FRONTEND=%REPO%\frontend"
set "VENV=%BACKEND%\.venv"
set "VENV_PY=%VENV%\Scripts\python.exe"
set "VENV_PIP=%VENV%\Scripts\pip.exe"

title Santander - Instalacion
echo ========================================
echo  Instalacion Control de Accesos
echo  Repo: %REPO%
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python no esta en PATH. Instala Python 3.11+ y marca "Add to PATH".
  pause
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo ERROR: npm no esta en PATH. Instala Node.js LTS.
  pause
  exit /b 1
)

echo == Entorno Python ^(backend\.venv^)
if not exist "%VENV_PY%" (
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo ERROR: No se pudo crear el venv.
    pause
    exit /b 1
  )
)
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail
"%VENV_PIP%" install -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto :fail

echo.
echo == Build del panel web ^(frontend\dist^)
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

if not exist "%BACKEND%\.env" (
  copy /y "%BACKEND%\.env.example" "%BACKEND%\.env" >nul
  echo.
  echo !! Creado backend\.env desde .env.example
  echo    Revisa: MODBUS_SERIAL_PORT / COM, JWT, COCE_*, CSIP_*, PANPHONE_*, TLS.
)

echo.
echo == Registro en inicio de Windows
call "%~dp04_registrar-inicio.bat" /nopause

echo.
echo ========================================
echo  Instalacion completada
echo ========================================
echo  Orden de scripts:
echo    1_instalar.bat           ^(esta vez^)
echo    2_arrancar.bat           ^(arranque manual / al encender^)
echo    3_actualizar.bat         ^(cuando haya nueva version^)
echo    4_registrar-inicio.bat   ^(re-registrar inicio^)
echo    5_quitar-inicio.bat      ^(quitar arranque automatico^)
echo.
echo  Panel: http://localhost:8000  ^(o la IP del PC^)
echo.
set /p STARTNOW=Arrancar el panel ahora? [S/N]: 
if /i "%STARTNOW%"=="S" (
  start "Santander Panel" "%~dp02_arrancar.bat"
)
exit /b 0

:fail
echo.
echo ERROR en la instalacion. Revisa los mensajes anteriores.
pause
exit /b 1
