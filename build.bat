@echo off
rem Build TPAutoClicker.exe on this PC.
rem Needs Python 3.9+ on PATH (python.org installer, tick "Add python.exe to PATH").
rem Result: dist\TPAutoClicker.exe
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist .venv (
  echo Creating build environment...
  python -m venv .venv || goto :fail
)
call .venv\Scripts\activate.bat || goto :fail

echo Installing dependencies...
python -m pip install --quiet --upgrade pip || goto :fail
python -m pip install --quiet -r requirements.txt pyinstaller pytest || goto :fail

echo Running tests...
set QT_QPA_PLATFORM=offscreen
python -m pytest -q || goto :fail
set QT_QPA_PLATFORM=

echo Building exe...
pyinstaller --noconfirm --log-level WARN tpautoclicker.spec || goto :fail

echo Checking the exe...
start /wait "" dist\TPAutoClicker.exe --self-test
if errorlevel 1 goto :fail

for %%F in (dist\TPAutoClicker.exe) do echo Done: %%~fF  (%%~zF bytes)
if "%1"=="" explorer dist
exit /b 0

:fail
echo.
echo Build failed - see the messages above.
if "%1"=="" pause
exit /b 1
