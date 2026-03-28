from __future__ import annotations

from collections.abc import Iterator
import logging
import socket

from .base import BaseTransport
from .encoding import decode_transport_bytes


class SocketJsonTransport(BaseTransport):
    def __init__(
        self,
        host: str,
        port: int,
        backlog: int = 1,
        buffer_size: int = 4096,
        logger: logging.Logger | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.backlog = backlog
        self.buffer_size = buffer_size
        self.logger = logger or logging.getLogger(__name__)
        self.server_socket: socket.socket | None = None
        self.client_socket: socket.socket | None = None
        self._reported_fallback_encoding = False

    def start(self) -> None:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(self.backlog)
        self.server_socket = server_socket
        self.logger.info("Listening for JSON socket stream on %s:%s", self.host, self.port)
        self.client_socket, address = server_socket.accept()
        self.logger.info("Socket client connected from %s:%s", address[0], address[1])

    def iter_messages(self) -> Iterator[str]:
        if self.client_socket is None:
            raise RuntimeError("Socket transport not started.")

        buffer = b""
        while True:
            chunk = self.client_socket.recv(self.buffer_size)
            if not chunk:
                self.logger.warning("Socket peer disconnected.")
                return

            buffer += chunk
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line, encoding = decode_transport_bytes(raw_line)
                if encoding not in {"utf-8", "utf-8-sig"} and not self._reported_fallback_encoding:
                    self.logger.warning(
                        "Socket payload was decoded with %s fallback. "
                        "This usually means the upstream process is not sending UTF-8.",
                        encoding,
                    )
                    self._reported_fallback_encoding = True

                message = line.strip()
                if message:
                    yield message

    def close(self) -> None:
        if self.client_socket is not None:
            self.client_socket.close()
            self.client_socket = None
        if self.server_socket is not None:
            self.server_socket.close()
            self.server_socket = None
