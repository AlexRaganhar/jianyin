@echo off
setlocal
set "TOOL_DIR=%~dp0"
set "PYTHONW=%TOOL_DIR%.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
  echo.
  echo 笺隐图形界面启动失败：未找到本地 Python 环境。
  echo 请先按 README.md 或运行 scripts\setup.cmd 完成安装。
  pause
  exit /b 1
)
pushd "%TOOL_DIR%"
"%PYTHONW%" -m jianyin_app.gui.app
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
  echo.
  echo 笺隐图形界面启动失败（exit code %EXIT_CODE%）。
  echo 启动错误日志位于 %%LOCALAPPDATA%%\JianYin\logs\startup.log。
  pause
)
endlocal & exit /b %EXIT_CODE%
