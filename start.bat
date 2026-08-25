@echo off
cd /d "%~dp0"
title OfflineTutor Launcher

echo [1/3] Checking Ollama...
powershell -NoProfile -Command "$c=Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue; if($c){'  Ollama already running'}; if(-not $c){ $s=(Get-Command ollama -ErrorAction SilentlyContinue).Source; if(-not $s){'  ERROR: Ollama not installed'}else{ Start-Process -WindowStyle Hidden -FilePath $s -ArgumentList 'serve'; $ok=$false; foreach($i in 1..40){ Start-Sleep 1; if(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue){$ok=$true;break} }; if($ok){'  Ollama started'}else{'  WARNING: Ollama did not respond in 40s'} } }"

if not exist .venv (
    echo [2/3] First-time setup...
    call setup.bat
) else (
    echo [2/3] Starting OfflineTutor server...
)
powershell -NoProfile -Command "$c=Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -match 'uvicorn' }; if($c){'  Server already running'}; if(-not $c){ Start-Process -WindowStyle Minimized -FilePath '%CD%\.venv\Scripts\python.exe' -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory '%CD%'; Start-Sleep 3; '  Server started' }"

echo [3/3] Opening dashboard...
start "" http://localhost:8000
echo.
echo All good - everything runs in the background.
echo To stop later: double-click stop.bat
pause
