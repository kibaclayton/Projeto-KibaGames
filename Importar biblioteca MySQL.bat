@echo off
setlocal
cd /d "%~dp0nexus-desktop"
echo Feche o Nexus antes de importar. O MySQL original sera preservado.
echo A senha sera solicitada localmente e nao sera exibida.
pause
powershell -NoProfile -File "scripts\import-mysql.ps1" -AskPassword
pause
