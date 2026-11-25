"""A local mock HTTP server that replays scripted responses."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

import pytest

from curl_sms import CurlSMS


@dataclass
class RecordedRequest:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


@dataclass
class ScriptedResponse:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    delay: float = 0.0


class MockServer:
    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []
        self._responses: deque[ScriptedResponse] = deque()
        self._lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self) -> None:
                parsed = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                with server._lock:
                    server.requests.append(
                        RecordedRequest(
                            method=self.command,
                            path=parsed.path,
                            query=urllib.parse.parse_qs(parsed.query),
                            headers={k.lower(): v for k, v in self.headers.items()},
                            body=body,
                        )
                    )
                    response = (
                        server._responses.popleft()
                        if server._responses
                        else ScriptedResponse(
                            500,
                            b'{"error":{"code":"internal","message":"no response queued"}}',
                        )
                    )
                if response.delay:
                    time.sleep(response.delay)
                try:
                    self.send_response(response.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(response.body)))
                    for name, value in response.headers.items():
                        self.send_header(name, value)
                    self.end_headers()
                    self.wfile.write(response.body)
                except OSError:
                    pass  # client gave up (timeout test)

            do_GET = _handle
            do_POST = _handle
            do_DELETE = _handle

            def log_message(self, format: str, *args: Any) -> None:
                pass

        class Server(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request: Any, client_address: Any) -> None:
                pass

        self._httpd = Server(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        self._thread.start()

    def respond(
        self,
        status: int,
        body: Any = None,
        *,
        headers: dict[str, str] | None = None,
        raw: bytes | None = None,
        delay: float = 0.0,
    ) -> None:
        data = raw if raw is not None else json.dumps(body).encode("utf-8")
        self._responses.append(ScriptedResponse(status, data, headers or {}, delay))

    def error(self, status: int, code: str, message: str = "Error.", **extra: Any) -> None:
        headers = extra.pop("headers", None)
        self.respond(
            status, {"error": {"code": code, "message": message, **extra}}, headers=headers
        )

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


@pytest.fixture
def server() -> Iterator[MockServer]:
    mock = MockServer()
    yield mock
    mock.close()


@pytest.fixture
def sleeps() -> list[float]:
    return []


@pytest.fixture
def client(server: MockServer, sleeps: list[float]) -> CurlSMS:
    c = CurlSMS("cs_test_example", base_url=server.url, timeout=5)
    c._sleep = sleeps.append
    return c


MESSAGE: dict[str, Any] = {
    "id": "01JDQ8M3V6R1T5ZK2X9N4C7B0A",
    "mode": "test",
    "receiver": "+4915123456789",
    "status": "queued",
    "segments": 1,
    "encoding": "gsm7",
    "price": "0.00",
    "error_code": None,
    "created_at": "2026-11-25T10:15:00.000Z",
    "send_at": None,
    "sent_at": None,
    "delivered_at": None,
    "refunded": False,
}
