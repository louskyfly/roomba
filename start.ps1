#Requires -Version 5.1
<#
    ROO-LAB — démarrage local
    Crée le venv Python si nécessaire, installe les dépendances,
    compile l'interface puis lance l'API (qui sert aussi le frontend).

    Usage :
        .\start.ps1
        .\start.ps1 -Port 8000
        .\start.ps1 -Rebuild      # force la recompilation du frontend
        .\start.ps1 -SkipBuild    # utilise dist/ tel quel
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Rebuild,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "    $Message" -ForegroundColor DarkGray
}

$venv   = Join-Path $PSScriptRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$backend = Join-Path $PSScriptRoot "backend"
$frontend = Join-Path $PSScriptRoot "frontend"
$distIndex = Join-Path $frontend "dist\index.html"

# ------------------------------------------------------------------ Python
if (-not (Test-Path $python)) {
    Write-Step "Création de l'environnement virtuel Python"
    $created = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) {
            & py -3.12 -m venv $venv
            $created = $LASTEXITCODE -eq 0
        } else {
            & py -3 -m venv $venv
            $created = $LASTEXITCODE -eq 0
        }
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venv
        $created = $LASTEXITCODE -eq 0
    }

    if (-not $created -or -not (Test-Path $python)) {
        throw "Python 3.12+ est introuvable. Installez-le (winget install Python.Python.3.12) puis relancez."
    }
    Write-Ok "venv créé dans .venv"
}

Write-Step "Vérification des dépendances backend"
& $python -c "import fastapi, uvicorn, paho.mqtt, cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Ok "installation de requirements.txt"
    & $python -m pip install --upgrade pip --quiet
    & $python -m pip install -r (Join-Path $backend "requirements.txt") --quiet
    if ($LASTEXITCODE -ne 0) { throw "Échec de l'installation des dépendances Python." }
}
Write-Ok "backend prêt"

# ---------------------------------------------------------------- Frontend
if (-not $SkipBuild) {
    $needBuild = $Rebuild -or -not (Test-Path $distIndex)
    if (-not $needBuild) {
        $distTime = (Get-Item $distIndex).LastWriteTimeUtc
        $newer = Get-ChildItem -Path (Join-Path $frontend "src"), (Join-Path $frontend "index.html"), (Join-Path $frontend "vite.config.ts") -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTimeUtc -gt $distTime } |
            Select-Object -First 1
        if ($newer) { $needBuild = $true }
    }

    if ($needBuild) {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            throw "npm est introuvable. Installez Node.js 20+ puis relancez, ou utilisez -SkipBuild avec un dist/ déjà compilé."
        }
        Write-Step "Compilation de l'interface"
        if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
            Write-Ok "npm install"
            Push-Location $frontend
            try { & npm install --no-fund --no-audit } finally { Pop-Location }
            if ($LASTEXITCODE -ne 0) { throw "Échec de npm install." }
        }

        # Certaines politiques npm bloquent le script postinstall d'esbuild.
        $esbuildExe = Join-Path $frontend "node_modules\@esbuild\win32-x64\esbuild.exe"
        if (-not (Test-Path $esbuildExe) -and (Test-Path (Join-Path $frontend "node_modules\esbuild\install.js"))) {
            Write-Ok "finalisation d'esbuild"
            Push-Location $frontend
            try { & node (Join-Path $frontend "node_modules\esbuild\install.js") } finally { Pop-Location }
        }

        Push-Location $frontend
        try {
            & npm run build
            if ($LASTEXITCODE -ne 0) { throw "Échec de la compilation du frontend." }
        } finally { Pop-Location }
        Write-Ok "interface compilée dans frontend\dist"
    } else {
        Write-Ok "interface déjà à jour"
    }
}

# ------------------------------------------------------------------- serveur
Write-Step "Démarrage de ROO-LAB"
Write-Host "    Interface : http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "    API       : http://127.0.0.1:$Port/api/health" -ForegroundColor DarkGray
Write-Host "    Ctrl+C pour arrêter." -ForegroundColor DarkGray

Push-Location $backend
try {
    & $python -m uvicorn app.main:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
