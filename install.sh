#!/usr/bin/env bash
# === Instalador do freeclaudio (macOS / Linux) ===
# Instala: dependencias Python, Claude Code, e adiciona 'freeclaudio' ao PATH.
# Execute: bash install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "=== freeclaudio - Instalador ==="
echo ""

# --- 1. Verificar Python ---
if ! command -v python3 &>/dev/null; then
    echo "[ERRO] Python3 nao encontrado. Instale Python 3.11+"
    exit 1
fi
echo "[OK] Python encontrado: $(python3 --version)"

# --- 2. Verificar Node.js ---
if ! command -v node &>/dev/null; then
    echo "[ERRO] Node.js nao encontrado. Instale Node.js 22+ de https://nodejs.org"
    exit 1
fi
echo "[OK] Node.js encontrado: $(node --version)"

# --- 3. Instalar dependencias Python ---
echo ""
echo "Instalando dependencias Python..."
python3 -m pip install -q fastapi uvicorn httpx
echo "[OK] Dependencias Python instaladas."

# --- 4. Instalar Claude Code ---
echo ""
echo "Verificando Claude Code..."

_install_claude() {
    npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code
    # Garantir postinstall caso ainda nao tenha rodado
    NPM_ROOT="$(npm root -g)"
    if [ -f "$NPM_ROOT/@anthropic-ai/claude-code/install.cjs" ]; then
        echo "Configurando binario nativo..."
        node "$NPM_ROOT/@anthropic-ai/claude-code/install.cjs" 2>/dev/null || true
    fi
    echo "[OK] Claude Code instalado."
}

if command -v claude &>/dev/null; then
    CLAUDE_DIR="$(dirname "$(command -v claude)")"
    CLAUDE_SIZE=$(stat -c%s "$CLAUDE_DIR/claude" 2>/dev/null || stat -f%z "$CLAUDE_DIR/claude" 2>/dev/null || echo 0)
    if [ -n "$CLAUDE_SIZE" ] && [ "$CLAUDE_SIZE" -gt 5000 ]; then
        echo "[OK] Claude Code ja esta instalado e funcional."
    else
        echo "[AVISO] binario do Claude invalido (stub). Reinstalando..."
        _install_claude
    fi
else
    echo "Claude Code nao encontrado. Instalando via npm..."
    _install_claude
fi

# --- 5. Criar symlink para 'freeclaudio' ---
echo ""
INSTALL_DIR="/usr/local/bin"
if [ ! -w "$INSTALL_DIR" ] 2>/dev/null; then
    INSTALL_DIR="$HOME/.local/bin"
    mkdir -p "$INSTALL_DIR"
fi

cat > "$INSTALL_DIR/freeclaudio" << LAUNCHER
#!/usr/bin/env bash
export PYTHONPATH="$SCRIPT_DIR:\${PYTHONPATH:-}"
cd "\$(pwd)"
exec python3 "$SCRIPT_DIR/freeclaudio/__main__.py" "\$@"
LAUNCHER
chmod +x "$INSTALL_DIR/freeclaudio"
echo "[OK] Comando 'freeclaudio' criado em $INSTALL_DIR/freeclaudio"

# Verificar se esta no PATH
if echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
    echo "[OK] $INSTALL_DIR ja esta no PATH."
else
    echo ""
    echo "[AVISO] $INSTALL_DIR nao esta no PATH."
    echo "Adicione ao seu shell profile (.bashrc, .zshrc, etc.):"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi

echo ""
echo "============================================"
echo " Instalacao concluida!"
echo "============================================"
echo ""
echo " 1. Edite providers.json com suas chaves de API"
echo " 2. Rode:  freeclaudio"
echo ""
