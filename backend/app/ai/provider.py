"""AI Provider interface.

Phase 1 builds the *foundation*: a stable provider abstraction, gateway,
prompt engine, and memory store. Later phases (AI Companion, Background
Intelligence) plug into this without touching the rest of the platform.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel


class AIConfig(BaseModel):
    provider: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: str


class ChatMessage(BaseModel):
    role: str  # system | user | assistant
    content: str


class AIResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: Optional[dict[str, Any]] = None


class AIProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        """Complete a chat conversation."""

    @abstractmethod
    async def ping(self, config: AIConfig) -> bool:
        """Check connectivity."""


class NoopProvider(AIProvider):
    """Default provider when no AI is configured. Keeps the gateway honest."""

    name = "none"

    async def chat(self, messages: list[ChatMessage], config: AIConfig) -> AIResponse:
        return AIResponse(content="", model="none", provider="none")

    async def ping(self, config: AIConfig) -> bool:
        return True
