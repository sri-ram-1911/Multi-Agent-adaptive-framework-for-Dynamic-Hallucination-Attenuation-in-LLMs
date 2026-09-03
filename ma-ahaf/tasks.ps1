<#
  Windows task runner (Makefile equivalent) — `make` is not standard on Windows.

  Usage:   .\tasks.ps1 <target>
  Targets: setup test lint demo demo-real demo-large up up-obs down migrate seed
           bootstrap-models eval frontend-dev help
#>
param(
  [Parameter(Position = 0)]
  [string]$Target = "help"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Py = Join-Path $Backend ".venv\Scripts\python.exe"

function Initialize-Venv {
  if (-not (Test-Path $Py)) {
    Write-Host "Creating venv + installing backend deps (first run, ~a few minutes)..." -ForegroundColor Cyan
    python -m venv (Join-Path $Backend ".venv")
    & $Py -m pip install --quiet --upgrade pip
    & $Py -m pip install --quiet --index-url https://download.pytorch.org/whl/cpu "torch>=2.2"
    Push-Location $Backend; & $Py -m pip install --quiet -e ".[dev]"; Pop-Location
  }
}

function Invoke-Backend([string[]]$ArgList, [hashtable]$EnvVars = @{}) {
  $old = @{}
  foreach ($k in $EnvVars.Keys) {
    $old[$k] = [Environment]::GetEnvironmentVariable($k)
    [Environment]::SetEnvironmentVariable($k, $EnvVars[$k])
  }
  try {
    Push-Location $Backend
    & $Py @ArgList
    $code = $LASTEXITCODE
    Pop-Location
  }
  finally {
    foreach ($k in $EnvVars.Keys) { [Environment]::SetEnvironmentVariable($k, $old[$k]) }
  }
  if ($code -ne 0) { exit $code }
}

switch ($Target) {
  "setup"            { Initialize-Venv; Write-Host "backend venv ready: $Py" -ForegroundColor Green }
  "test"            { Initialize-Venv; Invoke-Backend @("-m", "pytest", "-q") }
  "lint"            { Initialize-Venv; Invoke-Backend @("-m", "ruff", "check", "app", "scripts", "tests") }
  "demo"            { Initialize-Venv; Invoke-Backend @("-m", "scripts.demo", "--mock") }
  "demo-real"       { Initialize-Venv; Invoke-Backend @("-m", "scripts.demo", "--real", "--fast") -EnvVars @{ HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "demo-large"      { Initialize-Venv; Invoke-Backend @("-m", "scripts.demo", "--real", "--large") -EnvVars @{ HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "serve"          { Initialize-Venv; Invoke-Backend @("-m", "scripts.serve_demo", "--mock") }
  "serve-real"     { Initialize-Venv; Invoke-Backend @("-m", "scripts.serve_demo") -EnvVars @{ HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "dashboard" {
    Initialize-Venv
    if (-not (Get-Command node -EA SilentlyContinue)) {
      Write-Host "Node.js not found. Install it (one time) with:" -ForegroundColor Yellow
      Write-Host "    winget install OpenJS.NodeJS.LTS" -ForegroundColor Cyan
      Write-Host "close and reopen the terminal, then re-run:  .\tasks.ps1 dashboard" -ForegroundColor Yellow
      exit 1
    }
    $fe = Join-Path $Root "frontend"
    if (-not (Test-Path (Join-Path $fe "dist\index.html"))) {
      Write-Host "Building the dashboard (one time)..." -ForegroundColor Cyan
      Push-Location $fe
      if (-not (Test-Path "node_modules")) { npm install }
      npm run build
      Pop-Location
    }
    Write-Host ""
    Write-Host "  DASHBOARD  ->  http://localhost:8000" -ForegroundColor Green
    Write-Host "  (Ctrl+C to stop)" -ForegroundColor DarkGray
    Write-Host ""
    Invoke-Backend @("-m", "scripts.serve_demo", "--mock")
  }
  "dashboard-real" {
    Initialize-Venv
    $fe = Join-Path $Root "frontend"
    if (-not (Test-Path (Join-Path $fe "dist\index.html"))) {
      Push-Location $fe; if (-not (Test-Path "node_modules")) { npm install }; npm run build; Pop-Location
    }
    Write-Host "`n  DASHBOARD  ->  http://localhost:8000   (real local models)`n" -ForegroundColor Green
    Invoke-Backend @("-m", "scripts.serve_demo") -EnvVars @{ HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" }
  }
  "dashboard-openai" {
    Initialize-Venv
    $fe = Join-Path $Root "frontend"
    if (-not (Test-Path (Join-Path $fe "dist\index.html"))) {
      Push-Location $fe; if (-not (Test-Path "node_modules")) { npm install }; npm run build; Pop-Location
    }
    if (-not (Test-Path (Join-Path $Backend ".env"))) {
      Write-Host "backend\.env missing - put OPENAI_API_KEY=sk-... in it first" -ForegroundColor Yellow; exit 1
    }
    Write-Host "`n  DASHBOARD  ->  http://localhost:8000   (gpt-4o-mini)`n" -ForegroundColor Green
    Invoke-Backend @("-m", "scripts.serve_demo") -EnvVars @{ MAAHAF_LLM__PROVIDER = "openai"; MAAHAF_MAX_REVISION_LOOPS = "1"; OMP_NUM_THREADS = "4"; MKL_NUM_THREADS = "4"; HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" }
  }
  "serve-openai"   { Initialize-Venv; Invoke-Backend @("-m", "scripts.serve_demo") -EnvVars @{ MAAHAF_LLM__PROVIDER = "openai"; MAAHAF_MAX_REVISION_LOOPS = "1"; OMP_NUM_THREADS = "4"; MKL_NUM_THREADS = "4"; HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "eval-openai"    { Initialize-Venv; Invoke-Backend @("-m", "scripts.eval_local", "--limit", "77", "--timeout", "180") -EnvVars @{ MAAHAF_LLM__PROVIDER = "openai"; HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "capture"        { Initialize-Venv; Invoke-Backend @("-m", "scripts.capture_traces") -EnvVars @{ MAAHAF_LLM__PROVIDER = "openai"; MAAHAF_MAX_REVISION_LOOPS = "1" } }
  "bootstrap-models" { Initialize-Venv; Invoke-Backend @("-m", "scripts.bootstrap_models") }
  "eval"           { Initialize-Venv; Invoke-Backend @("-m", "scripts.run_eval", "--dataset", "data/benchmark/benchmark.jsonl") }
  "eval-local"     { Initialize-Venv; Invoke-Backend @("-m", "scripts.eval_local", "--limit", "40") -EnvVars @{ HF_HUB_OFFLINE = "1"; TRANSFORMERS_OFFLINE = "1" } }
  "retrain"        { Initialize-Venv; Invoke-Backend @("-m", "app.ml.retrain_from_eval") }
  "up"             { if (-not (Test-Path (Join-Path $Root ".env"))) { Copy-Item (Join-Path $Root ".env.example") (Join-Path $Root ".env"); Write-Host "created .env - set OPENAI_API_KEY" -ForegroundColor Yellow }; docker compose -f (Join-Path $Root "docker-compose.yml") up -d --build; docker compose -f (Join-Path $Root "docker-compose.yml") exec -T api alembic upgrade head }
  "up-obs"         { docker compose -f (Join-Path $Root "docker-compose.yml") --profile obs up -d --build }
  "down"           { docker compose -f (Join-Path $Root "docker-compose.yml") --profile obs down }
  "migrate"        { docker compose -f (Join-Path $Root "docker-compose.yml") exec -T api alembic upgrade head }
  "seed"           { docker compose -f (Join-Path $Root "docker-compose.yml") exec -T api python -m scripts.seed_kb; docker compose -f (Join-Path $Root "docker-compose.yml") exec -T api python -m scripts.seed_benchmark }
  "frontend-dev"   { Push-Location (Join-Path $Root "frontend"); npm install; npm run dev; Pop-Location }
  default {
    Write-Host @"
MA-AHAF task runner (Windows)

  .\tasks.ps1 setup             create backend venv + install deps
  .\tasks.ps1 test              run pytest
  .\tasks.ps1 lint              run ruff
  .\tasks.ps1 demo              instant mock demo (no downloads)
  .\tasks.ps1 demo-real         real ML/DL demo, local flan-t5-base (offline)
  .\tasks.ps1 demo-large        real demo with flan-t5-large
  .\tasks.ps1 dashboard         VISUAL: build + serve the dashboard at http://localhost:8000 (mock)
  .\tasks.ps1 dashboard-real    same, but with real local models (slower)
  .\tasks.ps1 dashboard-openai  same, running the pipeline on gpt-4o-mini (needs backend\.env)
  .\tasks.ps1 serve             just the no-DB demo API on :8000
  .\tasks.ps1 capture           write 5 real gpt-4o-mini traces to demo_traces.json
  .\tasks.ps1 bootstrap-models  download HF models + train sklearn artifacts
  .\tasks.ps1 eval-local        MA-AHAF vs baseline eval, no Postgres -> artifacts/eval/
  .\tasks.ps1 eval-openai       full 77-item eval on gpt-4o-mini
  .\tasks.ps1 retrain           retrain risk_model + calibrator from the latest eval labels
  .\tasks.ps1 up / up-obs / down / migrate / seed     docker compose stack
"@
  }
}
