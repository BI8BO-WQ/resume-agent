@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo Resume Delivery Agent
echo =====================

python --version >nul 2>&1
if errorlevel 1 (
  echo Python is not installed or not added to PATH.
  echo Please install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
  echo Please fill OPENAI_API_KEY in .env, then save and close Notepad.
  notepad ".env"
)

findstr /C:"sk-your-api-key-here" ".env" >nul 2>&1
if not errorlevel 1 (
  echo OPENAI_API_KEY still looks like the placeholder value.
  echo Please fill your own API key in .env, then save and close Notepad.
  notepad ".env"
)

echo Starting local backend: http://127.0.0.1:8787
start "" powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1; Start-Process 'http://127.0.0.1:8787'"
python server.py
pause
