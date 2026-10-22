$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
Set-Location $Root

Write-Host "编译检查……" -ForegroundColor Cyan
& $Python -m compileall -q jianyin_app
if ($LASTEXITCODE -ne 0) { throw "compileall failed" }

Write-Host "测试……" -ForegroundColor Cyan
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

Write-Host "依赖检查……" -ForegroundColor Cyan
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw "pip check failed" }

$Ruff = Join-Path $Root ".venv\Scripts\ruff.exe"
if (Test-Path $Ruff) {
    Write-Host "静态检查……" -ForegroundColor Cyan
    & $Ruff check jianyin_app tests
    if ($LASTEXITCODE -ne 0) { throw "ruff failed" }
}

Write-Host "验证完成。" -ForegroundColor Green
