@echo off
REM === Instalador do freeclaudio (Windows) ===
REM Instala: dependencias Python, Claude Code, e adiciona 'freeclaudio' ao PATH.
REM Execute: install.cmd   (ou clique duplo)
setlocal EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
REM remover barra final
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

echo.
echo === freeclaudio - Instalador ===
echo.

REM --- 1. Verificar Python ---
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado. Instale Python 3.11+ de https://www.python.org
    goto :end
)
echo [OK] Python encontrado:
python --version

REM --- 2. Verificar Node.js (necessario para Claude Code) ---
node --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Node.js nao encontrado. Instale Node.js 22+ de https://nodejs.org
    goto :end
)
echo [OK] Node.js encontrado:
node --version

REM --- 3. Instalar dependencias Python ---
echo.
echo Instalando dependencias Python...
python -m pip install -q fastapi uvicorn httpx
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Falha ao instalar dependencias Python.
    goto :end
)
echo [OK] Dependencias Python instaladas.

REM --- 4. Instalar Claude Code via npm ---
echo.
echo Verificando Claude Code...
REM validar se o binario e nativo (nao o stub de ~500 bytes de postinstall bloqueado)
where claude >nul 2>&1
if %ERRORLEVEL% NEQ 0 goto :install_claude
for /f "delims=" %%i in ('where claude') do set "CLAUDE_BIN=%%i"
if exist "!CLAUDE_BIN!" (
    for %%A in ("!CLAUDE_BIN!") do set "CLAUDE_SIZE=%%~zA"
    if defined CLAUDE_SIZE if !CLAUDE_SIZE! LSS 5000 (
        echo [AVISO] binario do Claude invalido (stub). Reinstalando...
        goto :install_claude
    )
)
echo [OK] Claude Code ja esta instalado e funcional.
goto :configured

:install_claude
echo Claude Code nao encontrado ou invalido. Instalando via npm...
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] npm nao encontrado. Instale Node.js de https://nodejs.org
    goto :end
)
REM --allow-scripts resolve o bloqueio do postinstall (secure-by-default do npm)
call npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code
if !ERRORLEVEL! NEQ 0 (
    echo [ERRO] Falha ao instalar Claude Code.
    goto :end
)
REM Garantir postinstall caso ainda nao tenha rodado
echo Configurando binario nativo do Claude Code...
for /f "tokens=*" %%i in ('npm root -g') do set "NPM_GLOBAL=%%i"
if exist "!NPM_GLOBAL!\@anthropic-ai\claude-code\install.cjs" (
    node "!NPM_GLOBAL!\@anthropic-ai\claude-code\install.cjs" 2>nul
)
echo [OK] Claude Code instalado.
:configured

REM --- 5. Adicionar ao PATH do usuario ---
echo.
where freeclaudio >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Adicionando freeclaudio ao PATH do usuario...
    set "CURRENT_PATH="
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "CURRENT_PATH=%%b"
    if "!CURRENT_PATH!"=="" (
        reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "%PROJECT_DIR%" /f >nul
    ) else (
        echo !CURRENT_PATH! | findstr /i /c:"%PROJECT_DIR%" >nul
        if !ERRORLEVEL! NEQ 0 (
            reg add "HKCU\Environment" /v Path /t REG_EXPAND_SZ /d "!CURRENT_PATH!;%PROJECT_DIR%" /f >nul
        )
    )
    echo [OK] PATH atualizado. Abra um NOVO terminal para usar 'freeclaudio'.
) else (
    echo [OK] freeclaudio ja esta no PATH.
)

echo.
echo ============================================
echo  Instalacao concluida!
echo ============================================
echo.
echo  1. Edite providers.json com suas chaves de API
echo  2. Abra um NOVO terminal
echo  3. Rode:  freeclaudio
echo.

:end
pause
