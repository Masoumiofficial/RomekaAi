"""Channel adapters share ONE core. No business logic lives in a bot."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session


@dataclass
class ChannelResult:
    ok: bool
    text: str
    data: dict | None = None
    buttons: list | None = None


class ChannelAdapter(ABC):
    name = "base"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def verify(self, headers: dict) -> bool: ...

    @abstractmethod
    def resolve_user(self, db: Session, external_id: str) -> int | None: ...

    @abstractmethod
    def handle_update(self, db: Session, payload: dict) -> ChannelResult: ...
