"""Servidor proxy local compatível com o protocolo Anthropic Messages.

O Claude Code é configurado com ANTHROPIC_BASE_URL apontando para este servidor.
Ele recebe as requisições no formato Anthropic, traduz para OpenAI Chat
Completions e as encaminha ao provider configurado em providers.json.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from . import convert
from .config import AppConfig, get_provider, provider_lookup


def build_app(config: AppConfig) -> FastAPI:
    app_state: dict[str, Any] = {"config": config}

    app = FastAPI(title="freeclaudio proxy", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if config.proxy.auth_enabled:
            token = config.proxy.auth_token
            auth_header = request.headers.get("authorization", "")
            expected = f"Bearer {token}"
            if not auth_header or auth_header.strip() != expected:
                return JSONResponse(status_code=401, content={"error": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models():
        items = []
        for provider in config.providers:
            if not provider.default_model:
                continue
            items.append(
                {
                    "id": provider.default_model,
                    "display_name": f"{provider.name}: {provider.default_model}",
                    "created": int(time.time()),
                    "type": "text",
                }
            )
            items.append(
                {
                    "id": f"{provider.name}/{provider.default_model}",
                    "display_name": f"{provider.name} (direto)",
                    "created": int(time.time()),
                    "type": "text",
                }
            )
        return {"data": items, "object": "list"}

    @app.post("/v1/messages/count_tokens")
    async def count_tokens(request: Request):
        body: dict[str, Any] = await request.json()
        text = _count_text(body)
        return {"input_tokens": _estimate_tokens(text)}

    @app.post("/v1/messages")
    async def messages(request: Request):
        body: dict[str, Any] = await request.json()
        model = str(body.get("model", "default"))
        try:
            provider, resolved_model = provider_lookup(
                config, config.default_provider, model
            )
        except ValueError as exc:
            return JSONResponse(status_code=502, content={"error": str(exc)})

        payload = convert.anthropic_messages_to_openai(body)
        payload["model"] = resolved_model

        try:
            if body.get("stream", True):
                return _stream_response(config, provider, payload, resolved_model)
            return await _nonstream_response(config, provider, payload, resolved_model)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=502, content={"error": str(exc)})

    return app


def _stream_response(
    config: AppConfig, provider, payload: dict[str, Any], model: str
) -> StreamingResponse:
    async def event_gen():
        headers = _headers(provider)
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        url = f"{provider.base_url}/chat/completions"

        yield _sse_encode(
            {
                "type": "message_start",
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            }
        )

        yielded_content = False
        text_buffered = ""
        thought_buffered = ""
        usage_out = 0

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    yield _sse_error_from_provider(
                        provider.name, resp.status_code, err_text
                    )
                    yield _sse_encode({"type": "message_stop"})
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    text, thought, tool_tc, finish, usage = _extract_chunk(chunk)
                    usage_out = usage or usage_out

                    if thought and not yielded_content:
                        if not thought_buffered:
                            yield _sse_encode(_content_block_start(0, "thinking"))
                        for phrase in _chunk_text(thought):
                            thought_buffered += phrase
                            yield _sse_encode(
                                {
                                    "type": "content_block_delta",
                                    "index": 0,
                                    "delta": {"type": "thinking_delta", "thinking": phrase},
                                }
                            )

                    if text:
                        if not yielded_content:
                            yield _sse_encode(_content_block_start(0, "text"))
                            yielded_content = True
                        for phrase in _chunk_text(text):
                            text_buffered += phrase
                            yield _sse_encode(
                                {
                                    "type": "content_block_delta",
                                    "index": 0,
                                    "delta": {"type": "text_delta", "text": phrase},
                                }
                            )

                    if tool_tc:
                        if not yielded_content:
                            yield _sse_encode(_content_block_start(0, "tool_use"))
                            yielded_content = True
                        yield _sse_encode(
                            {
                                "type": "content_block_delta",
                                "index": 0,
                                "delta": {
                                    "type": "input_json_delta",
                                    "partial_json": tool_tc.get("arguments", ""),
                                },
                            }
                        )

                    if finish:
                        break

        if yielded_content:
            yield _sse_encode({"type": "content_block_stop", "index": 0})
        yield _sse_encode(
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": usage_out},
            }
        )
        yield _sse_encode({"type": "message_stop"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _nonstream_response(config, provider, payload, model) -> Response:
    headers = _headers(provider)
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"
    url = f"{provider.base_url}/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            return JSONResponse(
                status_code=502,
                content={
                    "error": f"Provider {provider.name} retornou {resp.status_code}: "
                    f"{resp.text[:500]}"
                },
            )
        data = resp.json()
    anthropic = convert.openai_nonstream_to_anthropic(data, model)
    return JSONResponse(content=anthropic)


def _headers(provider) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _content_block_start(index: int, block_type: str) -> dict[str, Any]:
    base: dict[str, Any] = {"type": "content_block_start", "index": index}
    if block_type == "text":
        base["content_block"] = {"type": "text", "text": ""}
    elif block_type == "thinking":
        base["content_block"] = {"type": "thinking", "thinking": ""}
    elif block_type == "tool_use":
        base["content_block"] = {"type": "tool_use", "id": "toolu_1", "name": "tool", "input": {}}
    return base


def _chunk_text(text: str, size: int = 200) -> list[str]:
    """Quebra texto em pedaços para evitar eventos enormes."""
    if len(text) <= size:
        return [text] if text else []
    return [text[i : i + size] for i in range(0, len(text), size)]


def _extract_chunk(chunk: dict[str, Any]) -> tuple[str, str, dict | None, bool, int]:
    """Extrai texto, raciocínio, tool_call e finish de um chunk OpenAI."""
    text = ""
    thinking = ""
    tool_tc: dict | None = None
    finish = False
    usage = 0

    choices = chunk.get("choices", [])
    if not choices:
        usage = (chunk.get("usage") or {}).get("completion_tokens", 0)
        return text, thinking, tool_tc, finish, usage

    choice = choices[0]
    delta = choice.get("delta", {}) or {}

    if delta.get("reasoning_content"):
        thinking = delta["reasoning_content"]

    content = delta.get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text += part.get("text", "")

    tool_calls = delta.get("tool_calls")
    if tool_calls and tool_calls[0]:
        tool_tc = tool_calls[0]

    if choice.get("finish_reason"):
        finish = True

    return text, thinking, tool_tc, finish, usage


def _sse_encode(event: dict[str, Any]) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


def _sse_error_from_provider(provider_name: str, status: int, err_bytes: bytes) -> str:
    """Gera um evento Anthropic 'error' amigavel quando o provider falha.

    Retorna a string SSE completa com um texto claro para o usuario, com dica
    especifica para o erro mais comum: 401 = falta de API key.
    """
    raw = err_bytes.decode(errors="replace")[:500]
    message = _extract_provider_error_message(raw)
    hint = ""
    if status in (401, 403):
        hint = (
            "\n\n[freeclaudio] Dica: o provider retornou erro de autenticacao. "
            "Verifique a 'api_key' de '{}' no providers.json "
            "(valor real, ou 'env:NOME_DA_VAR' com a variavel definida)."
        ).format(provider_name)
    text = (
        f"O provider '{provider_name}' retornou um erro (HTTP {status}).\n"
        f"{message}{hint}"
    )
    event = {
        "type": "error",
        "error": {"type": "api_error", "message": text},
    }
    return _sse_encode(event)


def _extract_provider_error_message(raw: str) -> str:
    """Extrai a mensagem de erro legivel do corpo JSON do provider."""
    try:
        parsed = json.loads(raw)
        err = parsed.get("error")
        if isinstance(err, dict):
            return str(err.get("message", raw))
        if isinstance(err, str):
            return err
    except json.JSONDecodeError:
        pass
    return raw


def _count_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for msg in body.get("messages", []):
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def serve(config: AppConfig, log: bool = True) -> None:
    app = build_app(config)
    uvicorn.run(
        app,
        host=config.proxy.host,
        port=config.proxy.port,
        log_level="info" if log else "warning",
    )
