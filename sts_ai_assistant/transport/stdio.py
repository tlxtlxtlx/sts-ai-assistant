from __future__ import annotations

from collections.abc import Iterator, Mapping
import io
import logging
import sys

from .base import BaseTransport
from .encoding import decode_transport_bytes


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
        self._binary_input_stream = self._resolve_binary_input_stream(self.input_stream)
        self._reported_fallback_encoding = False
        self._configure_utf8_streams()

    def start(self) -> None:
        self._send_line("ready")
        self.logger.info("Communication Mod handshake sent.")

    def iter_messages(self) -> Iterator[str]:
        if self._binary_input_stream is not None:
            while True:
                raw_line = self._binary_input_stream.readline()
                if raw_line == b"":
                    self.logger.warning("stdin closed by Communication Mod.")
                    return

                line, encoding = decode_transport_bytes(raw_line)
                if encoding not in {"utf-8", "utf-8-sig"} and not self._reported_fallback_encoding:
                    self.logger.warning(
                        "Communication Mod input was decoded with %s fallback. "
                        "This usually means the upstream process is using a local Windows code page.",
                        encoding,
                    )
                    self._reported_fallback_encoding = True

                message = line.strip()
                if not message:
                    continue
                yield message

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
        streams = [self.output_stream]
        if self._binary_input_stream is None:
            streams.insert(0, self.input_stream)

        for stream in streams:
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except ValueError:
                    continue

    def _resolve_binary_input_stream(
        self,
        stream: io.TextIOBase | io.BufferedIOBase,
    ) -> io.BufferedIOBase | None:
        if isinstance(stream, io.BufferedIOBase):
            return stream

        buffer = getattr(stream, "buffer", None)
        if isinstance(buffer, io.BufferedIOBase):
            return buffer

        return None
