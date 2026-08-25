@echo off
cd /d "%~dp0"
echo Creating virtual environment (one-time setup)...
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
echo.
echo Setup complete! Run start.bat to launch OfflineTutor.
pause
