"""Provider-agnostic AI interface — the core never imports a vendor SDK."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class ChatMessage:
    role: str                      # system | user | assistant
    content: str

    def as_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatRequest:
    messages: list[ChatMessage]
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 900
    metadata: dict = field(default_factory=dict)


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    raw: dict = field(default_factory=dict)


class ProviderError(Exception):
    """Transient or permanent provider failure; never leaks secrets."""

    def __init__(self, message: str, *, retryable: bool = True, status_code: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


class BaseProvider(ABC):
    name = "base"
    is_external = False

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def chat(self, req: ChatRequest) -> ChatResult: ...

    def stream(self, req: ChatRequest) -> Iterator[str]:
        yield self.chat(req).text

    @abstractmethod
    def estimate_cost_usd(self, prompt_chars: int, completion_chars: int, model: str) -> float: ...
