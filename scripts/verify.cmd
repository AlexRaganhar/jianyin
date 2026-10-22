@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verify.ps1" %*
if errorlevel 1 (
  echo.
  echo Verification failed. See the output above.
  pause
)
exit /b %ERRORLEVEL%
