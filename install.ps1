# Instalador do freeclaudio (Windows)
# Instala: dependencias Python, Claude Code, e adiciona 'freeclaudio' ao PATH.
# Execute: .\install.ps1   OU   clique duplo no install.cmd
param(
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "=== freeclaudio - Instalador ===" -ForegroundColor Cyan
Write-Host ""

# 1. Verificar Python
try {
    $pyVer = python --version 2>&1
    Write-Host "[OK] Python: $pyVer" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Python nao encontrado. Instale Python 3.11+ de https://www.python.org" -ForegroundColor Red
    exit 1
}

# 2. Verificar Node.js
try {
    $nodeVer = node --version 2>&1
    Write-Host "[OK] Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "[ERRO] Node.js nao encontrado. Instale Node.js 22+ de https://nodejs.org" -ForegroundColor Red
    exit 1
}

# 3. Instalar dependencias Python
Write-Host ""
Write-Host "Instalando dependencias Python (fastapi, uvicorn, httpx)..."
python -m pip install -q fastapi uvicorn httpx
if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar dependencias Python." }
Write-Host "[OK] Dependencias Python instaladas." -ForegroundColor Green

# 4. Instalar Claude Code via npm
Write-Host ""
$claudePath = Get-Command claude -ErrorAction SilentlyContinue
if (-not $claudePath) {
    Write-Host "Claude Code nao encontrado. Instalando via npm..."
    $npmPath = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmPath) {
        Write-Host "[ERRO] npm nao encontrado. Instale Node.js de https://nodejs.org" -ForegroundColor Red
        exit 1
    }
    npm install -g @anthropic-ai/claude-code
    if ($LASTEXITCODE -ne 0) { throw "Falha ao instalar Claude Code." }

    # Rodar postinstall para baixar binario nativo
    Write-Host "Configurando binario nativo do Claude Code..."
    $npmRoot = (npm root -g).Trim()
    $installCjs = Join-Path $npmRoot "@anthropic-ai\claude-code\install.cjs"
    if (Test-Path $installCjs) {
        node $installCjs 2>$null
    }
    Write-Host "[OK] Claude Code instalado." -ForegroundColor Green
} else {
    Write-Host "[OK] Claude Code ja esta instalado: $($claudePath.Source)" -ForegroundColor Green
}

# 5. Adicionar ao PATH do usuario
Write-Host ""
if (-not $NoPath) {
    $current = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($current -notlike "*$ProjectDir*") {
        $newPath = if ([string]::IsNullOrEmpty($current)) { $ProjectDir } else { "$current;$ProjectDir" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "[OK] Adicionado '$ProjectDir' ao PATH do usuario." -ForegroundColor Green
        Write-Host "     Abra uma NOVA janela do terminal para 'freeclaudio' funcionar." -ForegroundColor Yellow
    } else {
        Write-Host "[OK] freeclaudio ja esta no PATH." -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Instalacao concluida!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " 1. Edite providers.json com suas chaves de API"
Write-Host " 2. Abra um NOVO terminal"
Write-Host " 3. Rode:  freeclaudio"
Write-Host ""
