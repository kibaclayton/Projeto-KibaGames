@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -File "nexus-desktop\scripts\update-shortcut.ps1"
if errorlevel 1 echo Nao foi possivel atualizar o atalho. Abra Abrir Nexus.bat diretamente.
pause
