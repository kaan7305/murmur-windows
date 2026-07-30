@echo off
REM Murmur - local voice to text. Double-click to start.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No virtualenv found. Run setup.bat first.
  pause
  exit /b 1
)
if "%~1"=="" (
  REM app.py hides its own console at startup; pythonw is avoided because it
  REM fails to create the window on this setup.
  start "" ".venv\Scripts\python.exe" app.py
) else (
  ".venv\Scripts\python.exe" murmur.py %*
  pause
)
