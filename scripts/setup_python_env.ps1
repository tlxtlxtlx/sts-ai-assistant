param()

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$env:PIP_CACHE_DIR = Join-Path $Root ".pip-cache"
New-Item -ItemType Directory -Force $env:PIP_CACHE_DIR | Out-Null

if (-not (Test-Path ".venv")) {
    python -m venv --copies .venv
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    & $python -m pip install -r requirements.txt
}

Write-Output "Python environment ready: $python"
Write-Output "PIP cache: $env:PIP_CACHE_DIR"
