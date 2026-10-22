@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
if errorlevel 1 (
  echo.
  echo Setup failed. See the output above.
  pause
)
exit /b %ERRORLEVEL%
