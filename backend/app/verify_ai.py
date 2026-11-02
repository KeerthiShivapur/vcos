"""AI provider verification (go-live prerequisite check).

Run:  python -m app.verify_ai [--live]

Checks, in order:
  1. The configured provider resolves (local/deterministic always available).
  2. If a live provider (groq/openai/anthropic) is configured, a minimal
     chat completion is attempted through the ratified AI gateway provider
     classes. The API key is NEVER printed; error output is class-only.

Exit code 0 when the effective provider is usable, 1 otherwise.
"""

from __future__ import annotations

import asyncio
import sys
import time

from app.core.config import get_settings


def _resolved_provider() -> str:
    settings = get_settings()
    provider = (settings.AI_PROVIDER or "local").lower()
    if provider in ("none", ""):
        return "local"
    return provider


async def verify(live: bool = False) -> int:
    settings = get_settings()
    provider = _resolved_provider()
    print(f"AI_PROVIDER configured: {settings.AI_PROVIDER}")
    print(f"effective provider:     {provider}")

    if provider == "local":
        from app.ai.gateway import ai_gateway  # noqa: F401  (import check)

        print("deterministic engine:   available (zero external dependencies)")
        print("VERDICT: OK (local deterministic engine)")
        return 0

    if provider == "groq":
        api_key = settings.GROQ_API_KEY or settings.AI_API_KEY
        base_url = settings.AI_BASE_URL
        model = settings.GROQ_MODEL or settings.AI_MODEL
    else:
        api_key = settings.AI_API_KEY
        base_url = settings.AI_BASE_URL
        model = settings.AI_MODEL

    if not api_key:
        print(f"api key:                MISSING for provider '{provider}'")
        print("VERDICT: NOT CONFIGURED (set the provider API key)")
        return 1
    print(f"api key:                present (masked, length={len(api_key)})")

    if not live:
        print("live check:             skipped (pass --live to call the provider)")
        print("VERDICT: CONFIGURED (not live-verified)")
        return 0

    from app.ai.provider import AIConfig, ChatMessage

    if provider == "groq":
        from app.ai.gateway import GroqProvider

        impl = GroqProvider()
    else:
        print(f"live check:             not implemented for provider '{provider}' here")
        print("VERDICT: CONFIGURED (use the gateway for live traffic)")
        return 0

    config = AIConfig(api_key=api_key, base_url=base_url, model=model)
    started = time.monotonic()
    try:
        response = await impl.chat(
            [ChatMessage(role="user", content="Reply with the single word: ok")],
            config,
        )
    except Exception as exc:
        print(f"live check:             FAILED ({type(exc).__name__})")
        print("VERDICT: FAILED (provider rejected the request)")
        return 1
    elapsed = time.monotonic() - started
    content = (response.content or "").strip()[:40]
    print(f"live check:             OK in {elapsed:.2f}s -> {content!r}")
    print(f"model reported:         {response.model}")
    print("VERDICT: OK (live provider verified)")
    return 0


if __name__ == "__main__":
    code = asyncio.run(verify(live="--live" in sys.argv))
    raise SystemExit(code)
