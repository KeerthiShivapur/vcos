"""AI Client for LLM interactions.

Provides unified interface for chat completions, embeddings, and streaming.
Supports multiple providers (OpenAI-compatible, local, etc.).
"""

import logging
from typing import Any, AsyncGenerator, Optional

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AIClient:
    """Unified AI client for chat completions and embeddings."""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_url = self.settings.AI_BASE_URL or "https://api.openai.com/v1"
        self.api_key = self.settings.AI_API_KEY
        self.model = self.settings.AI_MODEL or "gpt-4o-mini"
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        return self._client
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """Non-streaming chat completion."""
        client = await self._get_client()
        
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        try:
            response = await client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return {
                "content": data["choices"][0]["message"]["content"],
                "usage": data.get("usage", {}),
                "model": data.get("model", model or self.model),
            }
        except httpx.HTTPError as e:
            logger.error(f"AI chat request failed: {e}")
            raise
    
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        model: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming chat completion."""
        client = await self._get_client()
        
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as response:
                response.raise_for_status()
                
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            import json
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPError as e:
            logger.error(f"AI stream request failed: {e}")
            raise
    
    async def embeddings(
        self,
        texts: list[str],
        model: Optional[str] = None,
    ) -> list[list[float]]:
        """Generate embeddings for texts."""
        client = await self._get_client()
        
        payload = {
            "model": model or self.settings.EMBEDDING_MODEL or "text-embedding-3-small",
            "input": texts,
        }
        
        try:
            response = await client.post("/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
            
            return [item["embedding"] for item in data["data"]]
        except httpx.HTTPError as e:
            logger.error(f"AI embeddings request failed: {e}")
            raise
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


_ai_client: Optional[AIClient] = None


def get_ai_client() -> AIClient:
    """Get singleton AI client instance."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client


async def close_ai_client():
    """Close AI client (for shutdown)."""
    global _ai_client
    if _ai_client:
        await _ai_client.close()
        _ai_client = None