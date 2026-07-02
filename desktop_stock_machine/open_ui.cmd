@echo off
setlocal

set "UI_FILE=%~dp0frontend\index.html"

if not exist "%UI_FILE%" (
  echo Desktop Stock Machine UI was not found:
  echo %UI_FILE%
  echo.
  echo Make sure this launcher stays inside the desktop_stock_machine folder.
  pause
  exit /b 1
)

if /I "%~1"=="--check" (
  echo %UI_FILE%
  exit /b 0
)

start "" "%UI_FILE%"
exit /b 0
