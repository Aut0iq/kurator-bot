@echo off
cd /d "%~dp0"
if not exist .env if exist .env.example copy .env.example .env >nul
if not exist .venv (python -m venv .venv)
call .venv\Scripts\activate
pip install -q -r requirements.txt

set "URL="
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"WEBAPP_URL" .env') do set "URL=%%b"
set "URL=%URL: =%"
set "URL=%URL:https://=%"
if defined URL if "%URL:~-1%"=="/" set "URL=%URL:~0,-1%"
echo %URL% | find /i "ngrok" >nul
if not errorlevel 1 (
  tasklist /fi "imagename eq ngrok.exe" | find /i "ngrok.exe" >nul
  if errorlevel 1 (
    where ngrok >nul 2>nul
    if errorlevel 1 (
      if exist ngrok.exe (start "ngrok" /min ngrok.exe http --url=%URL% 8080) else (echo ngrok not found - start it manually: ngrok http --url=%URL% 8080)
    ) else (
      start "ngrok" /min ngrok http --url=%URL% 8080
    )
    echo ngrok: https://%URL%
  ) else (
    echo ngrok already running
  )
)

echo.
echo Starting bot... (Ctrl+C to stop)
python bot\main.py
pause
