from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from threading import Thread

from sts_ai_assistant.service.assistant_service import AssistantService
from sts_ai_assistant.service.state_store import LatestStateStore


class ApiServer:
    def __init__(
        self,
        host: str,
        port: int,
        state_store: LatestStateStore,
        assistant_service: AssistantService,
        logger: logging.Logger | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.state_store = state_store
        self.assistant_service = assistant_service
        self.logger = logger or logging.getLogger(__name__)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: Thread | None = None

    def start(self) -> None:
        state_store = self.state_store
        assistant_service = self.assistant_service
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self._send_cors_headers()
                self.end_headers()

            def do_GET(self) -> None:
                if self.path == "/api/health":
                    self._write_json({"status": "ok"})
                    return

                if self.path == "/api/state":
                    self._write_json(state_store.get_payload())
                    return

                self._write_json(
                    {"error": "Not found", "path": self.path},
                    status=HTTPStatus.NOT_FOUND,
                )

            def do_POST(self) -> None:
                if self.path == "/api/assistant/analyze":
                    body = self._read_json_body()
                    if body is None:
                        return
                    source = str(body.get("source") or "web")
                    focus = body.get("focus")
                    focus_text = str(focus).strip() if focus is not None else None
                    reply = assistant_service.analyze(source=source, focus=focus_text or None)
                    self._write_json(reply.to_dict())
                    return

                if self.path == "/api/assistant/chat":
                    body = self._read_json_body()
                    if body is None:
                        return
                    source = str(body.get("source") or "web")
                    message = str(body.get("message") or "").strip()
                    if not message:
                        self._write_json(
                            {"error": "message is required"},
                            status=HTTPStatus.BAD_REQUEST,
                        )
                        return
                    reply = assistant_service.chat(source=source, message=message)
                    self._write_json(reply.to_dict())
                    return

                self._write_json(
                    {"error": "Not found", "path": self.path},
                    status=HTTPStatus.NOT_FOUND,
                )

            def log_message(self, format: str, *args: object) -> None:
                logger.debug("API | " + format, *args)

            def _read_json_body(self) -> dict[str, object] | None:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(content_length)
                if not raw:
                    return {}
                try:
                    payload = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    self._write_json(
                        {"error": "Invalid JSON body"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return None
                if not isinstance(payload, dict):
                    self._write_json(
                        {"error": "JSON body must be an object"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return None
                return payload

            def _write_json(
                self,
                payload: dict[str, object],
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.logger.info("API server listening on http://%s:%s", self.host, self.port)

    def close(self) -> None:
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None
