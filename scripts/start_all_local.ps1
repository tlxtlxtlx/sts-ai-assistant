param()

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$env:PIP_CACHE_DIR = Join-Path $Root ".pip-cache"
$env:npm_config_cache = Join-Path $Root ".npm-cache"
$env:GRADLE_USER_HOME = Join-Path $Root ".gradle"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

New-Item -ItemType Directory -Force $env:PIP_CACHE_DIR | Out-Null
New-Item -ItemType Directory -Force $env:npm_config_cache | Out-Null
New-Item -ItemType Directory -Force $env:GRADLE_USER_HOME | Out-Null

$backend = Start-Process -FilePath (Join-Path $Root ".venv\Scripts\python.exe") `
    -ArgumentList ".\scripts\communication_mod_listener.py", "--config", ".\config\app_config.local.json" `
    -WorkingDirectory $Root `
    -PassThru

$frontend = Start-Process -FilePath "cmd.exe" `
    -ArgumentList "/c", "npm.cmd --prefix frontend run dev -- --host 127.0.0.1" `
    -WorkingDirectory $Root `
    -PassThru

Write-Output "Backend PID: $($backend.Id)"
Write-Output "Frontend PID: $($frontend.Id)"
Write-Output "PIP cache: $env:PIP_CACHE_DIR"
Write-Output "NPM cache: $env:npm_config_cache"
Write-Output "Gradle home: $env:GRADLE_USER_HOME"
