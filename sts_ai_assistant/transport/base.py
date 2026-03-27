from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping


class BaseTransport(ABC):
    @abstractmethod
    def start(self) -> None:
        """Prepare the transport."""

    @abstractmethod
    def iter_messages(self) -> Iterator[str]:
        """Yield newline-delimited JSON messages as strings."""

    def after_message(self, payload: Mapping[str, object] | None) -> None:
        """Optional hook after processing a message."""

    @abstractmethod
    def close(self) -> None:
        """Release transport resources."""
