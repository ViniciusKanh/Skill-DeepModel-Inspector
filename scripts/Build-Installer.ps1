# Gera o instalador Windows: frontend (npm) -> executavel (PyInstaller) -> Setup.exe (Inno Setup 6).
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\Build-Installer.ps1 [-Version 1.0.0]
# Requisitos: Python 3.11+, Node 18+, Inno Setup 6 (ISCC.exe). Nada e publicado automaticamente.
param([string]$Version = "1.0.0")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/4] Python build environment (.venv-build)"
if (-not (Test-Path ".venv-build")) { python -m venv .venv-build }
$Py = Join-Path $Root ".venv-build\Scripts\python.exe"
& $Py -m pip install --quiet --upgrade pip
& $Py -m pip install --quiet "fastapi>=0.110" "uvicorn>=0.29" "pyinstaller>=6.0"

Write-Host "[2/4] Frontend build"
Push-Location frontend
if (-not (Test-Path "node_modules")) { npm ci }
npm run build
Pop-Location
& $Py examples\generate_synthetic.py | Out-Null

Write-Host "[3/4] PyInstaller (onedir)"
& $Py -m PyInstaller --noconfirm --distpath build\pyinstaller\dist --workpath build\pyinstaller\work desktop\deepmodel.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "[4/4] Inno Setup"
$Iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) { $Iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $Iscc)) {
  Write-Host "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php and run again." -ForegroundColor Yellow
  Write-Host "Portable build is ready at build\pyinstaller\dist\DeepModelInspector\DeepModelInspector.exe"
  exit 0
}
& $Iscc "/DAppVersion=$Version" desktop\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Compress-Archive -Force -Path build\pyinstaller\dist\DeepModelInspector -DestinationPath "build\release\DeepModelInspector-$Version-portable-win64.zip"
Get-ChildItem build\release | ForEach-Object { "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash, $_.Name } | Set-Content build\release\SHA256SUMS.txt
Write-Host "Done: build\release" -ForegroundColor Green
