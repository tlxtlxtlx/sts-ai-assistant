@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
.\.venv\Scripts\python.exe .\scripts\communication_mod_listener.py --config .\config\app_config.local.json
