# Home GPU worker install (Windows) - task-20a. Idempotent: safe to re-run.
# ONE venv (.venv) runs the agent AND its in-process engines (scene_gen,
# voxcpm import torch/diffusers inside the agent's own process, so they
# must live together; Blackwell/sm_120 needs CUDA 12.8+ PyTorch - R12).
# SadTalker/MuseTalk are the exception: 2023-era research pins that clash
# with modern diffusers, so they run as subprocesses via a SEPARATE venv
# the owner sets up per setup.md (config.toml's `engines_python`).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== AI Video Maker GPU worker setup ==" -ForegroundColor Cyan

# 1. The worker venv
$venv = Join-Path $root ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating worker venv..."
    python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r (Join-Path $root "requirements.txt")

# 2. PyTorch CUDA 12.8 builds (Blackwell sm_120), then diffusers/voxcpm
Write-Host "Installing PyTorch CUDA 12.8 builds (~3 GB download)..." -ForegroundColor Yellow
& $py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
& $py -m pip install -r (Join-Path $root "requirements-engines.txt")

# 3. Sanity: does torch actually see the card? (risk R12's moment of truth)
& $py -c "import torch; ok = torch.cuda.is_available(); print('CUDA available:', ok, '| device:', torch.cuda.get_device_name(0) if ok else 'n/a')"

# 4. Config
$config = Join-Path $root "config.toml"
if (-not (Test-Path $config)) {
    Copy-Item (Join-Path $root "config.example.toml") $config
    Write-Host "Created config.toml - EDIT IT NOW:" -ForegroundColor Yellow
    Write-Host "  1. vm_url  = your site's public URL"
    Write-Host "  2. token   = the WORKER_TOKEN from the VM's env file"
} else {
    Write-Host "config.toml already exists - left untouched."
}

Write-Host ""
Write-Host "Next: see setup.md for the optional SadTalker/MuseTalk checkouts"
Write-Host "(their own venv -> config.toml engines_python) and the scene_gen"
Write-Host "bake-off (judgment gate #3). Then run:"
Write-Host "  .venv\Scripts\python.exe -m worker_agent" -ForegroundColor Green
