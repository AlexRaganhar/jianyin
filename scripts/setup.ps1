param(
    [string]$ModelSource = "",
    [switch]$SkipModel
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "笺隐初始化：$Root" -ForegroundColor Cyan

if (-not (Test-Path $Python)) {
    Write-Host "创建 Python 3.12 虚拟环境……"
    py -3.12 -m venv (Join-Path $Root ".venv")
}

Write-Host "安装项目依赖……"
& $Python -m pip install --upgrade pip --disable-pip-version-check
$InstallSpec = "$Root" + "[dev]"
& $Python -m pip install -e $InstallSpec --disable-pip-version-check

$ModelDest = Join-Path $Root "models\openai-privacy-filter-q4"
if (-not $SkipModel) {
    $HasModel = Test-Path (Join-Path $ModelDest "onnx\model_q4.onnx_data")
    if ($HasModel) {
        Write-Host "模型已存在，跳过模型准备。"
    }
    elseif ($ModelSource -and (Test-Path (Join-Path $ModelSource "onnx\model_q4.onnx_data"))) {
        Write-Host "从指定目录复制 Q4 ONNX 模型（约 945 MB）……"
        New-Item -ItemType Directory -Force $ModelDest | Out-Null
        robocopy $ModelSource $ModelDest /E /NFL /NDL /NJH /NJS /NP | Out-Null
    }
    else {
        Write-Host "未找到本地模型，尝试从 Hugging Face 下载……"
        & $Python -m jianyin_app.cli download-model
    }
}

Write-Host ""
Write-Host "安装完成。" -ForegroundColor Green
Write-Host "启动图形界面：$Root\启动图形界面.cmd"
Write-Host "运行测试：$Python -m pytest -q"
