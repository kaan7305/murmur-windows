@echo off
REM Build Murmur for distribution. Produces, in dist\:
REM
REM   Murmur-Setup-1.0.0.exe   the installer people download  (~120 MB)
REM   Murmur-GPU-Pack.zip      optional CUDA libraries        (~1.6 GB)
REM
REM   build.bat            installer only
REM   build.bat --gpu      installer and GPU pack
REM
REM Requires setup.bat to have been run, plus pyinstaller and Inno Setup 6.
setlocal
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe
if not exist "%PY%" (
  echo No virtualenv. Run setup.bat first.
  exit /b 1
)

REM Inno Setup installs per-user by default and system-wide when elevated;
REM check both rather than assume.
set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 not found. Install it with:
  echo   winget install JRSoftware.InnoSetup
  exit /b 1
)

echo [1/4] icon
"%PY%" -c "import sys; from PySide6 import QtGui; a=QtGui.QGuiApplication(sys.argv); import logo; logo.write_ico('murmur.ico')" || goto :fail

echo [2/4] freezing the application
"%PY%" -m PyInstaller --noconfirm --clean murmur.spec || goto :fail

echo [3/4] checking the build actually runs
del "%LOCALAPPDATA%\Murmur\selftest.txt" 2>nul
"dist\Murmur\Murmur.exe" --selftest
type "%LOCALAPPDATA%\Murmur\selftest.txt"
findstr /c:"PASSED" "%LOCALAPPDATA%\Murmur\selftest.txt" >nul || goto :selftest_failed

echo [4/4] building the installer
%ISCC% /Q murmur.iss || goto :fail

if /i "%~1"=="--gpu" (
  echo [+] building the GPU pack
  "%PY%" make_gpu_pack.py || goto :fail
)

echo.
echo Done.
dir /b dist\*.exe dist\*.zip 2>nul
exit /b 0

:selftest_failed
echo.
echo The frozen build failed its self test - see the output above.
echo Not building an installer around a broken program.
exit /b 1

:fail
echo.
echo Build failed.
exit /b 1
