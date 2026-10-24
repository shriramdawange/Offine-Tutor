@echo off
cd /d "%~dp0"
title API-Integrated Tutor

REM Load local environment variables from .env without requiring python-dotenv.
if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

echo [1/3] Checking Ollama for local fallback...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue; if($c){'  Ollama already running'}; if(-not $c){ $s=(Get-Command ollama -ErrorAction SilentlyContinue).Source; if($s){ Start-Process -WindowStyle Hidden -FilePath $s -ArgumentList 'serve'; '  Started Ollama for fallback'}else{'  Ollama not found; cloud mode can still work, but local fallback requires Ollama'} }"

if not exist .venv (
    echo [2/3] First-time setup...
    call setup.bat
) else (
    echo [2/3] Starting API-Integrated Tutor server...
)
powershell -NoProfile -Command "$c=Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn' }; if($c){'  Server already running'}; if(-not $c){ Start-Process -WindowStyle Minimized -FilePath '%CD%\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory '%CD%'; Start-Sleep 3; '  Server started' }"

echo [3/3] Opening dashboard...
start "" http://localhost:8000
echo.
echo Cloud API is tried first when API_KEY is configured; Ollama is the automatic fallback.
echo To stop later: double-click stop.bat
pause
