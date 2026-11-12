<#
.SYNOPSIS
  Inicia o DeepModel Inspector localmente (API FastAPI + frontend).

.DESCRIPTION
  Modo padrao (producao): a API serve o frontend ja compilado em frontend\dist em
  http://127.0.0.1:8765 - requer apenas Python 3.11+ com fastapi e uvicorn.
  Modo -Dev: inicia a API (8765) e o servidor Vite (5173) com recarga automatica - requer Node.js 18+.
  O script NAO instala dependencias nem altera configuracoes globais do Windows; ele apenas
  verifica e informa os comandos necessarios.

.EXAMPLE
  .\scripts\Start-DeepModel.ps1
  .\scripts\Start-DeepModel.ps1 -Port 8800
  .\scripts\Start-DeepModel.ps1 -Dev
#>
[CmdletBinding()]
param(
  [int]$Port = 8765,
  [switch]$Dev,
  [switch]$NoBrowser
)
$ErrorActionPreference = "Continue"  # erros de comandos nativos sao tratados explicitamente
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Fail($msg) { Write-Host "[DeepModel] ERROR: $msg" -ForegroundColor Red; exit 1 }
function Info($msg) { Write-Host "[DeepModel] $msg" -ForegroundColor Green }

# 1. Python (prefere o ambiente virtual do projeto)
$Python = $null
foreach ($cand in @("$Root\.venv\Scripts\python.exe", "py", "python")) {
  try {
    if ($cand -eq "py") { $v = & py -3 -c "import sys;print(sys.version_info[:2]>=(3,11))" 2>$null; if ($v -eq "True") { $Python = "py"; break } }
    elseif (Test-Path $cand -ErrorAction SilentlyContinue) { $v = & $cand -c "import sys;print(sys.version_info[:2]>=(3,11))"; if ($v -eq "True") { $Python = $cand; break } }
    elseif ($cand -eq "python" -and (Get-Command python -ErrorAction SilentlyContinue)) { $v = & python -c "import sys;print(sys.version_info[:2]>=(3,11))"; if ($v -eq "True") { $Python = "python"; break } }
  } catch { }
}
if (-not $Python) { Fail "Python 3.11+ not found. Install it from https://www.python.org/downloads/ and create the venv: py -3.13 -m venv .venv" }
$PyArgs = @(); if ($Python -eq "py") { $PyArgs = @("-3") }
Info "Python: $Python"

# 2. Dependencias da API
& $Python @PyArgs -c "import fastapi, uvicorn, deepmodel_inspector" 2>$null
if ($LASTEXITCODE -ne 0) {
  Fail "Missing Python packages. Activate the venv and run:  pip install -e "".[app]""   (fastapi, uvicorn and the engine)"
}

# 3. Frontend
if ($Dev) {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Fail "Node.js 18+ is required for -Dev. Install from https://nodejs.org/ or run without -Dev." }
  if (-not (Test-Path "$Root\frontend\node_modules")) { Fail "Frontend dependencies missing. Run:  cd frontend; npm ci" }
} elseif (-not (Test-Path "$Root\frontend\dist\index.html")) {
  Fail "Production build not found (frontend\dist). Build it with:  .\scripts\Build-Frontend.ps1   or start with -Dev."
}

# 4. Porta livre
$busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($busy) { Fail "Port $Port is already in use. Choose another one: -Port 8800" }

Info "Starting local API on http://127.0.0.1:$Port (localhost only)..."
$api = Start-Process -FilePath $Python -ArgumentList ($PyArgs + @("-m", "backend.api.main", "--port", "$Port")) -WorkingDirectory $Root -PassThru -NoNewWindow
Start-Sleep -Seconds 2
if ($api.HasExited) { Fail "API exited early (code $($api.ExitCode)). Run manually to see the error:  $Python -m backend.api.main --port $Port" }

$url = "http://127.0.0.1:$Port"
$vite = $null
try {
  if ($Dev) {
    $env:DMI_API_PORT = "$Port"
    Info "Starting Vite dev server on http://127.0.0.1:5173 ..."
    $vite = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory "$Root\frontend" -PassThru -NoNewWindow
    $url = "http://127.0.0.1:5173"
    Start-Sleep -Seconds 3
  }
  try { Invoke-RestMethod "http://127.0.0.1:$Port/api/status" -TimeoutSec 5 | Out-Null; Info "Backend status: online" }
  catch { Write-Host "[DeepModel] Warning: API not answering yet; check the console output above." -ForegroundColor Yellow }
  Write-Host ""
  Write-Host "  DeepModel Inspector is running:  $url" -ForegroundColor Cyan
  Write-Host "  Press Ctrl+C to stop." -ForegroundColor Cyan
  # Dica para iniciantes: verifica se ha um servidor de modelos local (Ollama) em execucao
  $ollama = Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue
  if ($ollama) { Info "Ollama detected on port 11434 (Model Lab > Connect a model > On this computer)." }
  else { Write-Host "[DeepModel] Tip: no Ollama server found. Open the Ollama app (or run 'ollama serve' in another terminal) to inspect local models." -ForegroundColor Yellow }
  if (-not $NoBrowser) { Start-Process $url }
  # Mantem o script ativo enquanto a API estiver rodando (Ctrl+C encerra)
  while (-not $api.HasExited) { Start-Sleep -Seconds 1 }
  Write-Host "[DeepModel] API process exited (code $($api.ExitCode)). Run manually to see errors: $Python -m backend.api.main --port $Port" -ForegroundColor Yellow
} finally {
  if ($vite -and -not $vite.HasExited) { Stop-Process -Id $vite.Id -Force -ErrorAction SilentlyContinue }
  if ($api -and -not $api.HasExited) { Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue }
  Info "Stopped."
}
