# Home GPU worker install (Windows) - task-20a. Idempotent: safe to re-run.
# Creates the agent venv + the engines venv (Blackwell/sm_120 needs CUDA
# 12.8+ PyTorch builds - risk R12), and seeds config.toml.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== AI Video Maker GPU worker setup ==" -ForegroundColor Cyan

# 1. Agent venv (tiny: requests + tray)
$agentVenv = Join-Path $root ".venv"
if (-not (Test-Path $agentVenv)) {
    Write-Host "Creating agent venv..."
    python -m venv $agentVenv
}
& (Join-Path $agentVenv "Scripts\python.exe") -m pip install --upgrade pip
& (Join-Path $agentVenv "Scripts\python.exe") -m pip install -r (Join-Path $root "requirements.txt")

# 2. Engines venv (torch cu128 first, then diffusers etc.)
$enginesVenv = Join-Path $root "engines-venv"
if (-not (Test-Path $enginesVenv)) {
    Write-Host "Creating engines venv..."
    python -m venv $enginesVenv
}
$enginesPy = Join-Path $enginesVenv "Scripts\python.exe"
& $enginesPy -m pip install --upgrade pip
Write-Host "Installing PyTorch CUDA 12.8 builds (Blackwell sm_120)..." -ForegroundColor Yellow
& $enginesPy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
& $enginesPy -m pip install -r (Join-Path $root "requirements-engines.txt")

# 3. Sanity: does torch actually see the card?
& $enginesPy -c "import torch; ok = torch.cuda.is_available(); print('CUDA available:', ok, '| device:', torch.cuda.get_device_name(0) if ok else 'n/a')"

# 4. Config
$config = Join-Path $root "config.toml"
if (-not (Test-Path $config)) {
    Copy-Item (Join-Path $root "config.example.toml") $config
    Write-Host "Created config.toml - EDIT IT NOW:" -ForegroundColor Yellow
    Write-Host "  1. vm_url  = your site's public URL"
    Write-Host "  2. token   = the WORKER_TOKEN from the VM's env file"
    Write-Host "  3. engines_python = $enginesPy"
} else {
    Write-Host "config.toml already exists - left untouched."
}

Write-Host ""
Write-Host "Next: see setup.md for SadTalker/MuseTalk checkouts and the"
Write-Host "scene_gen bake-off (judgment gate #3). Then run:"
Write-Host "  .venv\Scripts\python.exe -m worker_agent" -ForegroundColor Green
