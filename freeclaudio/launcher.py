"""Lógica do comando 'freeclaudio': sobe o proxy e roda o Claude Code junto."""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


# Tamanho do stub invalido do claude.exe quando o postinstall nao roda
# (arquivo de texto de ~500 bytes com mensagem de erro, nao um binario nativo)
_CLAUDE_STUB_MAX_BYTES = 5000


def ensure_claude_installed() -> str:
    """Garante que o claude-code CLI esta instalado e funcional.

    Alem de achar o binario, valida que o claude.exe NAO e o stub de 500 bytes
    que resulta quando o postinstall do npm e bloqueado (allowScripts). Se for,
    reinstala com --allow-scripts. Retorna o caminho do binario valido.
    """
    claude = _find_claude_binary()
    if claude and _looks_like_native_binary(claude):
        return claude

    print("Claude Code invalido ou ausente. Reinstalando via npm...")
    npm = _find_npm()
    if npm is None:
        raise RuntimeError(
            "npm nao encontrado. Instale o Node.js 18+ e rode "
            "`npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code`."
        )

    # --allow-scripts resolve o bloqueio do postinstall (secure-by-default do npm)
    result = subprocess.run(
        [
            npm, "install", "-g",
            "--allow-scripts=@anthropic-ai/claude-code",
            "@anthropic-ai/claude-code",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Falha ao instalar @anthropic-ai/claude-code via npm. "
            "Rode manualmente: npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code"
        )

    claude = _find_claude_binary()
    if not claude:
        raise RuntimeError("Claude Code instalado mas nao encontrado no PATH.")
    if not _looks_like_native_binary(claude):
        raise RuntimeError(
            "O claude.exe instalado parece ser um stub (postinstall bloqueado). "
            "Rode manualmente: node \"<npm-global>/@anthropic-ai/claude-code/install.cjs\""
        )
    return claude


def _find_claude_binary() -> str | None:
    claude = shutil.which("claude")
    if claude:
        return claude
    return None


def _looks_like_native_binary(path: str) -> bool:
    """True se o arquivo for um binario nativo grande, nao o stub de texto de erro."""
    try:
        size = Path(path).stat().st_size
        # O stub do claude.exe tem ~500 bytes; o binario nativo tem dezenas de MB
        return size > _CLAUDE_STUB_MAX_BYTES
    except OSError:
        return False


def _find_npm() -> str | None:
    npm = shutil.which("npm")
    if npm:
        return npm
    npm_cmd = shutil.which("npm.cmd")
    if npm_cmd:
        return npm_cmd
    return None


def _discover_providers_json() -> Path:
    """Procura o providers.json a partir do cwd ou da pasta deste pacote."""
    candidates = [
        Path.cwd() / "providers.json",
        Path(__file__).resolve().parent.parent / "providers.json",
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return Path.cwd() / "providers.json"


def _package_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _is_proxy_ready(host: str, port: int, auth_token: str) -> bool:
    import httpx

    try:
        headers = (
            {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        )
        resp = httpx.get(f"http://{host}:{port}/health", headers=headers, timeout=2.0)
        return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def run():
    from .config import load_config

    config_path = _discover_providers_json()
    config = load_config(config_path)
    host = config.proxy.host
    port = config.proxy.port
    token = config.proxy.auth_token

    ensure_deps()

    proxy_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "freeclaudio.proxy_serve",
            "--config",
            str(config_path),
        ],
        env={
            **os.environ,
            "FREECLAUDIO_CFG": str(config_path),
            "PYTHONPATH": str(_package_dir())
            + os.pathsep
            + os.environ.get("PYTHONPATH", ""),
        },
    )

    try:
        if not _wait_for_readiness(host, port, token, timeout=30):
            print(
                f"[erro] Proxy não ficou pronto em http://{host}:{port} dentro de 30s."
            )
            proxy_process.terminate()
            sys.exit(1)

        claude = ensure_claude_installed()

        env = {
            **os.environ,
            "ANTHROPIC_BASE_URL": f"http://{host}:{port}",
            "ANTHROPIC_AUTH_TOKEN": token,
            "ANTHROPIC_BEDROCK_VERTEX_PROXY": "0",
            "DISABLE_AUTOUPDATER": "1",
            "DISABLE_FEEDBACK_COMMAND": "1",
            "DISABLE_ERROR_REPORTING": "1",
            "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        }

        print(f"freeclaudio: proxy em http://{host}:{port} | rodando claude-code...\n")
        claude_proc = subprocess.run([claude, *sys.argv[1:]], env=env)
        return claude_proc.returncode
    finally:
        _terminate(proxy_process)


def _wait_for_readiness(host, port, token, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _is_proxy_ready(host, port, token):
            return True
        time.sleep(0.5)
    return False


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    for _ in range(50):
        if proc.poll() is not None:
            return
        time.sleep(0.1)
    proc.kill()


def ensure_deps() -> None:
    """Garante que as dependências Python (fastapi, uvicorn, httpx) estão presentes."""
    try:
        import fastapi  # noqa: F401
        import httpx  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        print("Instalando dependências (fastapi, uvicorn, httpx)...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "httpx"]
        )
        if result.returncode != 0:
            raise RuntimeError("Falha ao instalar dependências Python.")
