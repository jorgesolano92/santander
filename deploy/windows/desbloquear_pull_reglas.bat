@echo off
REM Compatibilidad: el desbloqueo ya esta dentro de 3_actualizar.bat
echo El desbloqueo de reglas esta integrado en 3_actualizar.bat
echo Lanzando actualizacion...
echo.
call "%~dp03_actualizar.bat"
exit /b %ERRORLEVEL%
