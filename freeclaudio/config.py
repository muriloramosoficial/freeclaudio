"""Carregamento e validação da configuração providers.json."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_CONFIG_PATH = Path("providers.json")


@dataclass
class ProviderConfig:
    name: str
    enabled: bool
    provider_type: str
    base_url: str
    api_key: str
    default_model: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProxyConfig:
    host: str = "127.0.0.1"
    port: int = 8082
    auth_token: str = "freeclaudio"
    auth_enabled: bool = True


@dataclass
class AppConfig:
    proxy: ProxyConfig
    providers: list[ProviderConfig]
    default_provider: str
    model_overrides: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _resolve_api_key(provider: dict[str, Any], name: str) -> str:
    """API key pode vir do json ou de uma variável de ambiente monitorada."""
    key = str(provider.get("api_key", "") or "")
    env_var_hint = "YOUR_" + name.upper()
    if key.startswith("env:"):
        env_name = key.split(":", 1)[1]
        return os.environ.get(env_name, "")
    if key and not key.startswith("YOUR_"):
        return key
    if key.startswith("YOUR_"):
        return ""
    return key


def load_config(path: Path | str | None = None) -> AppConfig:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Não encontrou {config_path}. Crie o arquivo providers.json "
            "(veja providers.json de exemplo)."
        )

    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))

    proxy_raw = raw.get("proxy", {})
    proxy = ProxyConfig(
        host=str(proxy_raw.get("host", "127.0.0.1")),
        port=int(proxy_raw.get("port", 8082)),
        auth_token=str(proxy_raw.get("auth_token", "freeclaudio")),
        auth_enabled=bool(proxy_raw.get("auth_enabled", True)),
    )

    providers: list[ProviderConfig] = []
    providers_raw = raw.get("providers", {}) or {}
    for name, p in providers_raw.items():
        providers.append(
            ProviderConfig(
                name=name,
                enabled=bool(p.get("enabled", True)),
                provider_type=str(p.get("type", "openai")),
                base_url=str(p.get("base_url", "")).rstrip("/"),
                api_key=_resolve_api_key(p, name),
                default_model=str(p.get("default_model", "")),
                extra=p,
            )
        )

    model_overrides: dict[str, str] = {}
    for k, v in (raw.get("model_overrides", {}) or {}).items():
        model_overrides[k] = str(v)

    return AppConfig(
        proxy=proxy,
        providers=[p for p in providers if p.enabled],
        default_provider=str(raw.get("default_provider", "")),
        model_overrides=model_overrides,
        raw=raw,
    )


def get_provider(config: AppConfig, name: str | None = None) -> ProviderConfig | None:
    target = name or config.default_provider
    for p in config.providers:
        if p.name == target:
            return p
    if config.providers:
        return config.providers[0]
    return None


def provider_lookup(
    config: AppConfig, provider_name: str | None, model: str
) -> tuple[ProviderConfig, str]:
    """Resolve o provider e o modelo a partir do id do modelo do cliente."""
    if "/" in model:
        candidate_provider, candidate_model = model.split("/", 1)
        for p in config.providers:
            if p.name == candidate_provider:
                return p, candidate_model
    provider = get_provider(config, provider_name)
    if provider is None:
        raise ValueError("Nenhum provider habilitado em providers.json")
    resolved_model = model
    if resolved_model in ("default", "", "claude", "claude-3-5-sonnet"):
        resolved_model = provider.default_model
    resolved_model = config.model_overrides.get(resolved_model, resolved_model)
    return provider, resolved_model
