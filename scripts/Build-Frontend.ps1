<#
.SYNOPSIS
  Build de produção do frontend (gera frontend\dist servido pela API).
  Requer Node.js 18+. Não instala nada globalmente.
#>
$ErrorActionPreference = "Continue"  # erros de comandos nativos são tratados explicitamente
$Root = Split-Path -Parent $PSScriptRoot
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { Write-Host "Node.js 18+ is required: https://nodejs.org/" -ForegroundColor Red; exit 1 }
Set-Location "$Root\frontend"
if (-not (Test-Path node_modules)) { Write-Host "Installing frontend dependencies locally (npm ci)…"; npm ci; if ($LASTEXITCODE) { exit 1 } }
npm run typecheck; if ($LASTEXITCODE) { exit 1 }
npm test; if ($LASTEXITCODE) { exit 1 }
npm run build; if ($LASTEXITCODE) { exit 1 }
Write-Host "Build complete: frontend\dist" -ForegroundColor Green
