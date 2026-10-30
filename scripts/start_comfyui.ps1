# Start the local ComfyUI server (http://127.0.0.1:8188) with the project venv.
$root = Split-Path -Parent $PSScriptRoot
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
Set-Location "$root\third_party\ComfyUI"
& "$root\.venv\Scripts\python.exe" main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch @args
