@echo off
setlocal
cd /d "%~dp0"
set "GAME_PYTHON=%LocalAppData%\Programs\Python\Python313\python.exe"
if not exist "%GAME_PYTHON%" (
  echo Python nao encontrado. Instale Python 3.13 ou ajuste este arquivo.
  pause
  exit /b 1
)
"%GAME_PYTHON%" -c "import mysql.connector; from PIL import Image, ImageTk" >nul 2>&1
if errorlevel 1 (
  echo Preparando os componentes na primeira abertura...
  "%GAME_PYTHON%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Nao foi possivel instalar os componentes. Confira sua conexao.
    pause
    exit /b 1
  )
)
"%GAME_PYTHON%" app.py
if errorlevel 1 pause
