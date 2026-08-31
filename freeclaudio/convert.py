"""Conversão entre o formato Anthropic Messages (Claude Code) e OpenAI Chat Completions.

O Claude Code usa o protocolo Anthropic (/v1/messages, SSE). A maioria dos
providers gratuitos expõe a API OpenAI (/chat/completions). Este módulo faz a
tradução nos dois sentidos.
"""
from __future__ import annotations

import json
import re
from typing import Any


SYSTEM_ROLE = "system"


def anthropic_messages_to_openai(body: dict[str, Any]) -> dict[str, Any]:
    """Converte o corpo da requisição Anthropic Messages para Chat Completions."""
    openai_messages: list[dict[str, Any]] = []

    system = body.get("system")
    if system:
        system_text = _flatten_system(system)
        if system_text:
            openai_messages.append({"role": "system", "content": system_text})

    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if isinstance(content, str):
            if content.strip():
                openai_messages.append({"role": role, "content": content})
            continue

        if isinstance(content, list):
            parts: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text":
                    parts.append({"type": "text", "text": block.get("text", "")})
                elif btype == "image":
                    parts.append(_image_block_to_openai(block))
                elif btype == "tool_use":
                    name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tool_id = block.get("id", f"toolu_{len(parts)}")
                    parts.append(
                        {
                            "type": "tool_call",
                            "id": tool_id,
                            "function": {"name": name, "arguments": json.dumps(tool_input)},
                        }
                    )
                elif btype == "tool_result":
                    tool_id = block.get("tool_use_id", f"toolu_{len(parts)}")
                    result = _flatten_tool_result(block.get("content"))
                    parts.append(
                        {
                            "type": "tool_result",
                            "tool_call_id": tool_id,
                            "content": result,
                        }
                    )
            if parts:
                openai_messages.append({"role": role, "content": parts})

    tools = []
    for tool in body.get("tools", []):
        name = tool.get("name", "")
        description = tool.get("description", "")
        input_schema = tool.get("input_schema", {"type": "object", "properties": {}})
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": input_schema,
                },
            }
        )

    payload: dict[str, Any] = {
        "messages": openai_messages,
        "stream": bool(body.get("stream", True)),
    }
    if tools:
        payload["tools"] = tools

    max_tokens = body.get("max_tokens")
    if isinstance(max_tokens, int):
        payload["max_tokens"] = max_tokens
    elif "max_completion_tokens" in body:
        payload["max_completion_tokens"] = body["max_completion_tokens"]

    temperature = body.get("temperature")
    if temperature is not None:
        payload["temperature"] = temperature

    top_p = body.get("top_p")
    if top_p is not None:
        payload["top_p"] = top_p

    thinking = body.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "enabled":
        budget = thinking.get("budget_tokens", 1024)
        payload["reasoning_effort"] = "high"
        payload["max_completion_tokens"] = (
            max_tokens if isinstance(max_tokens, int) else budget * 3
        )

    return payload


def _flatten_system(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        texts = []
        for block in system:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(str(block.get("text", "")))
                elif block.get("type") == "tool_choice" and isinstance(
                    block.get("tool_choice"), dict
                ):
                    pass
        return "\n".join(t for t in texts if t)
    return ""


def _flatten_tool_result(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(parts)
    if isinstance(content, dict):
        return json.dumps(content)
    return str(content)


def _image_block_to_openai(block: dict[str, Any]) -> dict[str, Any]:
    source = block.get("source", {})
    data = source.get("data", "")
    media_type = source.get("media_type", "image/png")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{data}"},
    }


def openai_chunk_to_anthropic_sse(chunk: dict[str, Any], model: str) -> list[dict[str, Any]]:
    """Converte um chunk de streaming OpenAI em eventos SSE Anthropic."""
    events: list[dict[str, Any]] = []
    choices = chunk.get("choices", [])
    if not choices:
        usage = chunk.get("usage")
        if usage and usage.get("output_tokens"):
            events.append(
                _message_delta(usage.get("output_tokens", 0))
            )
        return events

    choice = choices[0]
    delta = choice.get("delta", {}) or {}
    finish_reason = choice.get("finish_reason")

    if "reasoning_content" in delta and delta["reasoning_content"]:
        events.append(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {
                    "type": "thinking_delta",
                    "thinking": delta["reasoning_content"],
                },
            }
        )

    if "content" in delta:
        text = delta.get("content")
        if isinstance(text, str):
            events.append(
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": text},
                }
            )
        elif isinstance(text, list):
            for part in text:
                if isinstance(part, dict) and part.get("type") == "text":
                    events.append(
                        {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": part.get("text", "")},
                        }
                    )

    tool_calls = delta.get("tool_calls")
    if tool_calls:
        for tc in tool_calls:
            index = tc.get("index", 0)
            fn = tc.get("function", {})
            name = fn.get("name", "")
            arguments = fn.get("arguments", "")
            tool_id = tc.get("id", "")
            events.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": arguments,
                    },
                }
            )

    if finish_reason == "tool_calls":
        events.append({"type": "message_delta", "delta": {"stop_reason": "tool_use"}})
    elif finish_reason in ("stop", "length", "content_filter"):
        events.append({"type": "message_delta", "delta": {"stop_reason": "end_turn"}})

    return events


def openai_nonstream_to_anthropic(data: dict[str, Any], model: str) -> list[dict[str, Any]]:
    """Converte uma resposta completa (não-streaming) para resposta Anthropic."""
    content: list[dict[str, Any]] = []
    for choice in data.get("choices", []):
        message = choice.get("message", {})
        reasoning = message.get("reasoning_content")
        if reasoning:
            content.append({"type": "thinking", "thinking": reasoning})
        text = message.get("content")
        if isinstance(text, str) and text:
            content.append({"type": "text", "text": text})
        tool_calls = message.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                content.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", "toolu_1"),
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"].get("arguments", "{}")),
                    }
                )

    usage = data.get("usage", {})
    return {
        "id": data.get("id", "msg_claudiocode"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }


def _message_delta(output_tokens: int) -> dict[str, Any]:
    return {
        "type": "message_delta",
        "delta": {"stop_reason": None},
        "usage": {"output_tokens": output_tokens},
    }
