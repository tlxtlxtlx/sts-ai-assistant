from __future__ import annotations

from collections.abc import Iterator, Mapping
import io
import logging
import sys

from .base import BaseTransport


class CommunicationModStdioTransport(BaseTransport):
    def __init__(
        self,
        wait_frames: int = 30,
        input_stream: io.TextIOBase | None = None,
        output_stream: io.TextIOBase | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.wait_frames = max(wait_frames, 1)
        self.input_stream = input_stream or sys.stdin
        self.output_stream = output_stream or sys.stdout
        self.logger = logger or logging.getLogger(__name__)
        self._configure_utf8_streams()

    def start(self) -> None:
        self._send_line("ready")
        self.logger.info("Communication Mod handshake sent.")

    def iter_messages(self) -> Iterator[str]:
        while True:
            line = self.input_stream.readline()
            if line == "":
                self.logger.warning("stdin closed by Communication Mod.")
                return

            message = line.strip()
            if not message:
                continue
            yield message

    def after_message(self, payload: Mapping[str, object] | None) -> None:
        if not payload:
            self._send_line("STATE")
            return

        in_game = bool(payload.get("in_game", False))
        if in_game:
            self._send_line(f"WAIT {self.wait_frames}")
        else:
            self._send_line("STATE")

    def close(self) -> None:
        try:
            self.output_stream.flush()
        except BrokenPipeError:
            self.logger.warning("stdout pipe already closed.")

    def _send_line(self, line: str) -> None:
        try:
            self.output_stream.write(f"{line}\n")
            self.output_stream.flush()
        except BrokenPipeError:
            self.logger.exception("Failed to write command to Communication Mod.")
            raise

    def _configure_utf8_streams(self) -> None:
        for stream in (self.input_stream, self.output_stream):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except ValueError:
                    continue
