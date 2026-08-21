"""
LLM adapter for 1min.ai API.

1min.ai uses a custom API format (not OpenAI-compatible).
This module wraps their /api/chat-with-ai endpoint into a response
structure that matches what the orchestrator expects from litellm.completion().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.config import settings


@dataclass
class Message:
    content: str
    role: str = "assistant"


@dataclass
class Choice:
    message: Message
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class CompletionResponse:
    choices: list[Choice] = field(default_factory=list)
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)


async def one_min_ai_completion(
    messages: list[dict[str, str]],
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 600,
    **kwargs: Any,
) -> CompletionResponse:
    """
    Call 1min.ai's Chat with AI endpoint and return a litellm-compatible response.
    
    Converts the OpenAI-style messages array into 1min.ai's format:
    - System + user messages are combined into a single prompt
    - Uses their /api/chat-with-ai endpoint with API-KEY header
    """
    model = model or settings.LITELLM_MODEL

    # Combine system and user messages into a single prompt
    system_parts = []
    user_parts = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        elif msg["role"] == "user":
            user_parts.append(msg["content"])
        elif msg["role"] == "assistant":
            # Include assistant messages as context
            user_parts.append(f"[Previous response]: {msg['content']}")

    prompt = ""
    if system_parts:
        prompt += "System instructions:\n" + "\n".join(system_parts) + "\n\n"
    prompt += "\n".join(user_parts)

    payload = {
        "type": "UNIFY_CHAT_WITH_AI",
        "model": model,
        "promptObject": {
            "prompt": prompt,
            "settings": {
                "withMemories": False,
                "historySettings": {
                    "isMixed": False,
                    "historyMessageLimit": 10,
                },
                "webSearchSettings": {
                    "maxWord": 1000,
                    "numOfSite": 3,
                    "webSearch": False,
                },
            },
            "attachments": {"files": [], "images": []},
        },
    }

    async with httpx.AsyncClient(timeout=180.0, trust_env=True) as client:
        response = await client.post(
            "https://api.1min.ai/api/chat-with-ai",
            headers={
                "Content-Type": "application/json",
                "API-KEY": settings.ONE_MIN_AI_API_KEY,
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    # Extract result from 1min.ai response format
    ai_record = data.get("aiRecord", {})
    detail = ai_record.get("aiRecordDetail", {})
    result_list = detail.get("resultObject", [])
    result_text = result_list[0] if result_list else ""

    # Extract usage info
    metadata = ai_record.get("metadata", {})
    usage = {
        "prompt_tokens": metadata.get("inputToken", 0),
        "completion_tokens": metadata.get("outputToken", 0),
        "total_tokens": metadata.get("totalToken", 0),
    }

    return CompletionResponse(
        choices=[Choice(message=Message(content=result_text))],
        model=ai_record.get("model", model),
        usage=usage,
    )


def completion(
    model: str | None = None,
    messages: list[dict[str, str]] | None = None,
    temperature: float = 0.4,
    max_tokens: int = 600,
    **kwargs: Any,
) -> CompletionResponse:
    """
    Synchronous wrapper for one_min_ai_completion.
    Drop-in replacement for litellm.completion() when using 1min.ai.
    Works both inside and outside an existing event loop.
    """
    import asyncio

    coro = one_min_ai_completion(
        messages=messages or [],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to use asyncio.run
        return asyncio.run(coro)

    # Already in an event loop — use a new thread to avoid nested loop issues
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result(timeout=30)
