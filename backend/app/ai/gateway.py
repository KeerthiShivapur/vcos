"""Phase 7.1 — AI Gateway: the single entry point for every AI capability.

Never call an LLM directly. Everything goes through `ai_gateway`:

    request -> provider routing -> safety filter -> prompt build
            -> retry/stream -> response validation -> token accounting -> cache

Providers:
  - `groq`    Groq LPU inference (OpenAI-compatible wire protocol)
  - `openai`  OpenAI-compatible chat completions (any base URL)
  - `anthropic` Anthropic messages API
  - `local`   VCOS built-in deterministic intelligence engine — the product's
              own "LLM": grounded, rule-based, zero-cost, always available.
              Used automatically when no API key is configured.

Every call is accounted (tokens/requests) and cached where safe. The rest of
Phase 7 (companion, agents, search, planning) only ever talks to this gateway.
"""

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from typing import Any, AsyncIterator, Optional

from app.ai.provider import AIProvider, AIResponse, AIConfig, ChatMessage
from app.core.config import get_settings

logger = logging.getLogger("vcos.ai.gateway")

BLOCKED_PHRASES = (
    "generate malware",
    "exploit code",
    "hack into",
    "steal credentials",
    "write ransomware",
    "sql injection tutorial",
    "bypass authentication of",
)

_MAX_CACHE_ENTRIES = 256


class GroqProvider(AIProvider):
    """Groq LPU inference via its OpenAI-compatible endpoint."""

    name = "groq"

    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        return await self._complete(messages, config)

    async def chat_stream(self, messages: list[ChatMessage], config: AIConfig) -> AsyncIterator[str]:
        async for chunk in self._stream(messages, config):
            yield chunk

    async def _complete(self, messages, config) -> AIResponse:
        import httpx

        url = (config.base_url or "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": 0.2,
            "max_tokens": get_settings().AI_MAX_TOKENS,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return AIResponse(
            content=data["choices"][0]["message"]["content"] or "",
            model=data.get("model", config.model),
            provider=self.name,
            usage=data.get("usage"),
        )

    async def _stream(self, messages, config) -> AsyncIterator[str]:
        import httpx

        url = (config.base_url or "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [m.model_dump() for m in messages],
            "temperature": 0.2,
            "max_tokens": get_settings().AI_MAX_TOKENS,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        delta = json.loads(chunk)["choices"][0].get("delta", {}).get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta

    async def ping(self, config: AIConfig) -> bool:
        return bool(config.api_key)


class LocalIntelligenceEngine(AIProvider):
    """VCOS's built-in intelligence engine (the product's own "LLM").

    Deterministic and fully grounded: it answers from structured context
    passed in the system prompt and templates provided by the companion.
    It never invents facts — unknown inputs fall back to guidance text.
    """

    name = "local"

    async def ping(self, config: AIConfig) -> bool:
        return True

    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        return AIResponse(
            content=self._respond(messages),
            model=config.model,
            provider=self.name,
            usage={"prompt_tokens": sum(len(m.content) // 4 for m in messages), "completion_tokens": 0},
        )

    async def chat_stream(self, messages: list[ChatMessage], config: AIConfig) -> AsyncIterator[str]:
        content = self._respond(messages)
        for chunk in _chunk_text(content, size=24):
            yield chunk
            await asyncio.sleep(0.002)

    def _respond(self, messages: list[ChatMessage]) -> str:
        system = next((m.content for m in reversed(messages) if m.role == "system"), "")
        user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        directive = self._extract_directive(system)
        if directive == "structured":
            return self._structured(system, user)
        if directive == "brief":
            return self._brief(system, user)
        if directive == "suggest":
            return self._suggest(system, user)
        return self._default(user, system)

    @staticmethod
    def _extract_directive(system: str) -> Optional[str]:
        m = re.search(r"AI_DIRECTIVE=(\w+)", system)
        return m.group(1) if m else None

    def _structured(self, system: str, user: str) -> str:
        template = re.search(r"AI_TEMPLATE=(.*)", system, re.DOTALL)
        if template:
            return template.group(1).strip() or "No structured response available."
        return "No structured response available for this request."

    def _brief(self, system: str, user: str) -> str:
        brief = re.search(r"AI_BRIEF=(.*)", system, re.DOTALL)
        if brief and brief.group(1).strip():
            return brief.group(1).strip()
        if user.strip():
            return (
                f"Here is what I found about your request: {user[:200]}"
                "\n\nI'm running in local mode — connect a Groq API key in Settings "
                "for richer, free-form answers."
            )
        return "I don't have enough context to answer that yet."

    def _suggest(self, system: str, user: str) -> str:
        options = re.findall(r"AI_OPTION_(\d+)=(.*)", system)
        if options:
            lines = [f"{idx}. {text.strip()}" for idx, text in sorted(options, key=lambda t: int(t[0]))]
            return "\n".join(lines[:5])
        return "No suggestions available."

    def _default(self, user: str, system: str) -> str:
        org = "your organization"
        m = re.search(r"organization_name[:=]\s*([^\s,]+)", system)
        if m:
            org = m.group(1)
        return (
            f"I'm the AI Companion for {org}. I can plan your day, summarize "
            "projects/tasks/goals/meetings, search across the company, "
            "recommend experts and documents, predict risks, and run "
            "authorized actions. Try: 'What should I work on today?', "
            "'Org pulse', or 'Find an expert on React'."
        )


class OpenAILikeProvider(AIProvider):
    """OpenAI-compatible chat completions (OpenAI, or any compatible endpoint)."""

    name = "openai"

    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        import httpx

        url = (config.base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": config.model,
            "messages": [m.model_dump() for m in messages],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return AIResponse(
            content=data["choices"][0]["message"]["content"] or "",
            model=config.model,
            provider=self.name,
            usage=data.get("usage"),
        )

    async def ping(self, config: AIConfig) -> bool:
        return bool(config.api_key)


class AnthropicProvider(AIProvider):
    name = "anthropic"

    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        import httpx

        system = "\n".join(m.content for m in messages if m.role == "system")
        conversation = [m for m in messages if m.role != "system"]
        url = (config.base_url or "https://api.anthropic.com/v1").rstrip("/") + "/messages"
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model,
            "max_tokens": 2048,
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in conversation],
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        return AIResponse(
            content="".join(b.get("text", "") for b in data.get("content", [])),
            model=config.model,
            provider=self.name,
        )

    async def ping(self, config: AIConfig) -> bool:
        return bool(config.api_key)


class AIGateway:
    def __init__(self) -> None:
        self._providers: dict[str, AIProvider] = {
            "none": LocalIntelligenceEngine(),
            "local": LocalIntelligenceEngine(),
            "groq": GroqProvider(),
            "openai": OpenAILikeProvider(),
            "anthropic": AnthropicProvider(),
        }
        self._cache: dict[str, str] = {}
        self._stats: dict[str, int] = {"requests": 0, "tokens": 0, "cached": 0, "blocked": 0}
        self._lock = asyncio.Lock()

    def _config(self) -> AIConfig:
        settings = get_settings()
        provider = settings.AI_PROVIDER or "local"
        api_key = settings.GROQ_API_KEY or settings.AI_API_KEY
        if provider == "local" and settings.GROQ_API_KEY:
            provider = "groq"
        if provider == "groq" and not api_key:
            provider = "local"
        model = settings.GROQ_MODEL if provider == "groq" else settings.AI_MODEL
        return AIConfig(
            provider=provider,
            api_key=api_key,
            base_url=settings.AI_BASE_URL or "https://api.groq.com/openai/v1",
            model=model,
        )

    def provider(self) -> AIProvider:
        return self._providers.get(self._config().provider, self._providers["local"])

    # ------------------------------------------------------------------ safety

    def safety_check(self, text: str) -> Optional[str]:
        lowered = text.lower()
        for phrase in BLOCKED_PHRASES:
            if phrase in lowered:
                return f"Request blocked by the AI safety layer (matched policy: {phrase})."
        return None

    def _cache_key(self, provider: str, model: str, messages: list[ChatMessage]) -> str:
        digest = hashlib.sha256(json.dumps([m.model_dump() for m in messages], sort_keys=True).encode()).hexdigest()
        return f"{provider}:{model}:{digest}"

    # ------------------------------------------------------------------ calls

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        org_id: Optional[str] = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        config = self._config()
        self._stats["requests"] += 1
        blocked = self.safety_check("\n".join(m.content for m in messages))
        if blocked:
            self._stats["blocked"] += 1
            return {"available": True, "content": blocked, "model": config.model, "blocked": True, "usage": {}}
        cache_key = self._cache_key(config.provider, config.model, messages)
        if not stream and get_settings().AI_CACHE_ENABLED and cache_key in self._cache:
            self._stats["cached"] += 1
            return {
                "available": True,
                "content": self._cache[cache_key],
                "model": config.model,
                "cached": True,
                "usage": {},
            }
        provider = self.provider()
        attempts = get_settings().AI_RETRIES + 1
        last_error: Optional[str] = None
        for attempt in range(attempts):
            try:
                if stream:
                    chunks: list[str] = []
                    async for chunk in provider.chat_stream(messages, config):  # type: ignore[attr-defined]
                        chunks.append(chunk)
                    content = "".join(chunks)
                else:
                    response = await provider.chat(messages, config)
                    content = response.content
                content = self._validate(content)
                if content and cache_key not in self._cache:
                    self._cache[cache_key] = content
                    if len(self._cache) > _MAX_CACHE_ENTRIES:
                        self._cache.pop(next(iter(self._cache)))
                usage = getattr(response, "usage", {}) if not stream else {}
                tokens = (usage or {}).get("total_tokens") or (
                    (usage or {}).get("prompt_tokens", 0) + (usage or {}).get("completion_tokens", 0)
                )
                self._stats["tokens"] += tokens or (len(content) // 4)
                return {
                    "available": True,
                    "content": content,
                    "model": config.model,
                    "provider": config.provider,
                    "usage": usage,
                    "org_id": org_id,
                }
            except Exception as exc:  # retry with backoff
                last_error = str(exc)
                logger.warning("AI call attempt %s/%s failed: %s", attempt + 1, attempts, exc)
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
        return {"available": False, "content": None, "reason": last_error or "unknown", "model": config.model}

    async def stream(
        self, messages: list[ChatMessage], *, org_id: Optional[str] = None
    ) -> AsyncIterator[dict[str, Any]]:
        """SSE-friendly streaming with fallback to chunked local output."""
        config = self._config()
        self._stats["requests"] += 1
        blocked = self.safety_check("\n".join(m.content for m in messages))
        if blocked:
            yield {"type": "error", "content": blocked}
            return
        provider = self.provider()
        try:
            async for chunk in provider.chat_stream(messages, config):  # type: ignore[attr-defined]
                yield {"type": "chunk", "content": chunk}
        except Exception as exc:  # pragma: no cover - provider outage fallback
            logger.warning("AI stream failed, falling back to local: %s", exc)
            async for chunk in LocalIntelligenceEngine().chat_stream(messages, config):
                yield {"type": "chunk", "content": chunk}
        yield {"type": "done", "model": config.model}

    def _validate(self, content: str) -> str:
        text = (content or "").strip()
        if len(text) > 8000:
            text = text[:8000] + "…"
        return text

    async def status(self) -> dict[str, Any]:
        config = self._config()
        provider = self.provider()
        try:
            ok = await provider.ping(config)
        except Exception:
            ok = False
        if config.provider in ("none", "local"):
            effective, available, message = "local", True, "Running on the built-in VCOS intelligence engine"
        elif config.provider == "groq":
            effective, available = "groq", ok
            message = "Groq LLM ready" if ok else "Groq configured but unreachable"
        else:
            effective, available = config.provider, ok
            message = f"{config.provider} LLM ready" if ok else f"{config.provider} configured but unreachable"
        return {
            "available": available,
            "provider": effective,
            "configured": config.provider,
            "model": config.model,
            "mode": effective,
            "message": message,
            "stats": dict(self._stats),
        }

    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    def reset_cache(self) -> None:
        self._cache.clear()


ai_gateway = AIGateway()


def _chunk_text(text: str, size: int = 24) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]
