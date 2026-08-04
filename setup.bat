@echo off
REM One-time setup: creates the virtualenv and installs dependencies.
cd /d "%~dp0"
echo Creating virtualenv...
python -m venv .venv || goto :fail
echo Installing dependencies (a few hundred MB)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
echo.
echo Done. Run run.bat to start Murmur.
echo The speech model downloads on first launch (about 480 MB, once).
pause
exit /b 0

:fail
echo.
echo Setup failed. Is Python 3.10+ installed and on PATH?
pause
exit /b 1
