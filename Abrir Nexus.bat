@echo off
setlocal
cd /d "%~dp0nexus-desktop"
if not exist "release\latest.txt" (
  echo O Nexus precisa ser compilado. Consulte ATUALIZACAO-0.3.md.
  pause
  exit /b 1
)
set /p NEXUS_EXE=<"release\latest.txt"
if not exist "%NEXUS_EXE%" (
  echo Executavel nao encontrado. Compile novamente o aplicativo.
  pause
  exit /b 1
)
start "Nexus Wolf's" "%NEXUS_EXE%"
