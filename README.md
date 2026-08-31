# freeclaudio

Proxy local simples para rodar o **Claude Code** com providers gratuitos/locais
(Groq, OpenRouter, NVIDIA NIM, LM Studio, Ollama, etc.)
configurados via um unico arquivo `providers.json`.

Nao tem UI. Rode `freeclaudio` e ele sobe o proxy e lanca o Claude Code
apontando pra ele, tudo junto.

> Inspirado no conceito do [free-claude-code](https://github.com/alishahryar1/free-claude-code),
> mas simplificado, sem UI, e proprio. **Nao e afiliado a Anthropic.**

## Como funciona

```
Claude Code  ──Anthropic API──▶  freeclaudio (proxy)  ──OpenAI API──▶  Provider
  (CLI)                          127.0.0.1:8082                        (Groq/NIM/...)
```

O Claude Code pensa que fala com a Anthropic. O proxy traduz para OpenAI Chat
Completions e encaminha ao provider configurado.

## Instalacao

### Requisitos
- **Python 3.11+** ([python.org](https://www.python.org/downloads/))
- **Node.js 22+** ([nodejs.org](https://nodejs.org/))

### Windows

```powershell
git clone https://github.com/muriloramosoficial/freeclaudio.git
cd freeclaudio
.\install.cmd          # instala tudo (deps, Claude Code, PATH)
```

Ou via PowerShell com politica liberada:
```powershell
.\install.ps1
```

### macOS / Linux

```bash
git clone https://github.com/muriloramosoficial/freeclaudio.git
cd freeclaudio
bash install.sh        # instala tudo (deps, Claude Code, symlink)
```

### Apos instalar

1. Edite `providers.json` com suas chaves de API
2. Abra um **novo terminal**
3. Rode: `freeclaudio`

## providers.json

```json
{
  "proxy": {
    "host": "127.0.0.1",
    "port": 8082,
    "auth_token": "freeclaudio",
    "auth_enabled": true
  },
  "providers": {
    "openrouter": {
      "enabled": true,
      "base_url": "https://openrouter.ai/api/v1",
      "api_key": "SUA_CHAVE",
      "default_model": "free"
    },
    "groq": {
      "enabled": false,
      "base_url": "https://api.groq.com/openai/v1",
      "api_key": "env:GROQ_API_KEY",
      "default_model": "llama-3.3-70b-versatile"
    },
    "nvidia_nim": {
      "enabled": false,
      "base_url": "https://integrate.api.nvidia.com/v1",
      "api_key": "env:NVIDIA_NIM_API_KEY",
      "default_model": "nvidia/nemotron-3-super-120b-a12b"
    },
    "lmstudio": {
      "enabled": false,
      "base_url": "http://localhost:1234/v1",
      "api_key": "",
      "default_model": "local-model"
    },
    "ollama": {
      "enabled": false,
      "base_url": "http://localhost:11434/v1",
      "api_key": "",
      "default_model": "llama3.1"
    }
  },
  "default_provider": "openrouter"
}
```

## Uso

```bash
freeclaudio              # sobe proxy + Claude Code
freeclaudio --help       # passa args pro Claude Code
```

## Troubleshooting

### "claude.exe nao e compativel com esta versao do Windows" / Postinstall bloqueado

O npm moderno (com `allowScripts`) **bloqueia o postinstall** do claude-code por
seguranca. Quando isso acontece, o `claude.exe` vira um **stub invalido de ~500
bytes** (em vez do binario nativo de ~200MB), e o Claude Code nao abre.

Se o instalador ja usou `--allow-scripts`, rode manualmente:

```bash
npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code
```

O `freeclaudio` agora detecta esse stub automaticamente e tenta reinstalar. Se
ainda falhar, rode o postinstall manualmente:

```bash
# Windows
node "<npm-global>/@anthropic-ai/claude-code/install.cjs"

# macOS / Linux
npm root -g   # descobre o caminho
node "$(npm root -g)/@anthropic-ai/claude-code/install.cjs"
```

### Provider retorna 401 / "No cookie auth credentials found" / "api key"

Isso significa que o provider nao recebeu uma chave de API valida. Verifique o
`providers.json`:

- Preencha `api_key` com sua chave real (nao deixe `YOUR_...`)
- Ou use `"api_key": "env:NOME_DA_VARIAVEL"` e defina a variavel no ambiente

O proxy agora mostra uma mensagem clara com essa dica em vez de um stack trace.

### `freeclaudio` nao encontrado

No Windows, abra um **novo terminal** apos o `install.cmd` (o PATH pode nao
recarregar na sessao atual).

## Providers

Qualquer API compativel com OpenAI Chat Completions funciona:

| Provider            | base_url                                        |
|---------------------|-------------------------------------------------|
| OpenRouter (free)   | `https://openrouter.ai/api/v1`                  |
| Groq                | `https://api.groq.com/openai/v1`                |
| NVIDIA NIM          | `https://integrate.api.nvidia.com/v1`           |
| DeepSeek            | `https://api.deepseek.com/v1`                   |
| LM Studio (local)   | `http://localhost:1234/v1`                      |
| Ollama (local)      | `http://localhost:11434/v1`                     |
| llama.cpp (local)   | `http://localhost:8080/v1`                      |

### Chaves via variavel de ambiente

```json
"api_key": "env:OPENROUTER_API_KEY"
```

### Modelos por tier (opcional)

```json
"model_overrides": {
  "claude-3-5-sonnet-20241022": "nvidia_nim/nvidia/nemotron-3-super-120b-a12b",
  "claude-3-haiku-20240307": "groq/llama-3.3-70b-versatile"
}
```

## Seguranca

- Proxy em `127.0.0.1` (local only) por padrao
- Auth por token bearer habilitada por padrao
- Sem telemetria, sem exfiltracao, sem backdoors
- Sone conecta ao provider que voce configurar
- Source code aberto, auditar facil

## Estrutura

```
freeclaudio/
  __init__.py         # package init
  __main__.py         # python -m freeclaudio
  config.py           # le providers.json
  convert.py          # Anthropic <-> OpenAI traducao
  proxy.py            # servidor FastAPI
  proxy_serve.py      # subprocesso server
  launcher.py         # logica do comando freeclaudio
providers.json        # configuracao
freeclaudio.cmd       # launcher Windows
freeclaudio.sh        # launcher macOS/Linux
install.cmd           # instalador Windows (batch)
install.ps1           # instalador Windows (PowerShell)
install.sh            # instalador macOS/Linux
```

## Licenca

MIT
