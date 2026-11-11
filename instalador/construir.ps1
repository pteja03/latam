# Construye la app de escritorio y el instalador de Windows.
#
#   powershell -ExecutionPolicy Bypass -File instalador\construir.ps1
#
# Requisitos: Python 3.11+, `pip install ".[escritorio]"` e Inno Setup 6 (ISCC en el PATH).
# Resultado: dist\CREE-Agenda-Instalador-<version>.exe

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$version = python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
Write-Host "== CREE Agenda $version =="

# ---------- 1. Ejecutable (PyInstaller a traves de flet pack) ----------
flet pack escritorio/lanzador.py -y -D -n CreeAgenda `
  --icon instalador/icono.ico `
  --product-name "CREE Agenda" --file-description "CREE Agenda" `
  --company-name "Clinica CREE" --product-version $version --file-version $version `
  --add-data "migrations;migrations" `
  -- --paths=. --collect-submodules=app --collect-submodules=ui `
  --collect-submodules=escritorio --collect-submodules=uvicorn `
  --collect-submodules=alembic --collect-all=tzdata --hidden-import=asyncpg.pgproto.pgproto
if ($LASTEXITCODE -ne 0) { throw "Fallo la construccion del ejecutable" }

# ---------- 2. PostgreSQL portable ----------
$destino = Join-Path $raiz "build\postgres"
if (-not (Test-Path (Join-Path $destino "bin\postgres.exe"))) {
  New-Item -ItemType Directory -Force -Path $destino | Out-Null
  $origen = $env:CREE_POSTGRES_ORIGEN
  if (-not $origen -and $env:PGROOT -and (Test-Path (Join-Path $env:PGROOT "bin\postgres.exe"))) {
    $origen = $env:PGROOT   # instalacion existente (por ejemplo, la del runner de GitHub)
  }
  if (-not $origen) {
    $zip = Join-Path $raiz "build\postgres.zip"
    $url = "https://get.enterprisedb.com/postgresql/postgresql-16.6-1-windows-x64-binaries.zip"
    Write-Host "Descargando PostgreSQL: $url"
    Invoke-WebRequest -Uri $url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath (Join-Path $raiz "build\pg_tmp") -Force
    $origen = Join-Path $raiz "build\pg_tmp\pgsql"
  }
  Write-Host "PostgreSQL tomado de: $origen"
  foreach ($carpeta in "bin", "lib", "share") {
    Copy-Item -Recurse -Force (Join-Path $origen $carpeta) (Join-Path $destino $carpeta)
  }
  # Fuera lo que no se usa en tiempo de ejecucion.
  Get-ChildItem -Recurse $destino -Include *.pdb, *.lib, *.a | Remove-Item -Force
  Get-ChildItem (Join-Path $destino "bin") -Filter "stackbuilder*" | Remove-Item -Force
  # Runtime de Visual C++ junto a los binarios: funciona en una PC recien instalada.
  foreach ($dll in "vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll") {
    $ruta = Join-Path $env:WINDIR "System32\$dll"
    if (Test-Path $ruta) { Copy-Item -Force $ruta (Join-Path $destino "bin") }
  }
}
& (Join-Path $destino "bin\postgres.exe") --version
if ($LASTEXITCODE -ne 0) { throw "PostgreSQL empaquetado no funciona" }

# ---------- 3. Cloudflare Tunnel ----------
$tunel = Join-Path $raiz "build\cloudflared.exe"
if (-not (Test-Path $tunel)) {
  $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
  Invoke-WebRequest -Uri $url -OutFile $tunel
}

# ---------- 4. Instalador (Inno Setup) ----------
$env:CREE_VERSION = $version
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
& $iscc (Join-Path $PSScriptRoot "cree_agenda.iss")
if ($LASTEXITCODE -ne 0) { throw "Fallo la construccion del instalador" }
Get-ChildItem (Join-Path $raiz "dist") -Filter "CREE-Agenda-Instalador-*.exe" | Format-Table Name, Length
