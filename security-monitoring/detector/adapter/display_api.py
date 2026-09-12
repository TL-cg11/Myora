"""동일한 문맥 모델을 채팅 화면과 공유하는 loopback 전용 HTTP API."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Any

from adapter.pipeline import MaskingPipeline

MAX_BODY_BYTES = 50_000


class _Server(ThreadingHTTPServer):
    pipeline: MaskingPipeline


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def log_message(self, _format: str, *args: Any) -> None:
        # 요청 본문이나 모델 결과가 기본 access log에 섞이지 않게 한다.
        return

    def _json(self, status: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"detail": "NOT_FOUND"})

    def do_POST(self) -> None:
        if self.path != "/v1/mask":
            self._json(404, {"detail": "NOT_FOUND"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError
            data = json.loads(self.rfile.read(length))
            text = data.get("text") if isinstance(data, dict) else None
            display_text = self.server.pipeline.mask_display_text(text)
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            self._json(400, {"detail": "INVALID_DISPLAY_REQUEST"})
            return
        except Exception:
            self._json(503, {"detail": "DISPLAY_MASKING_UNAVAILABLE"})
            return
        self._json(200, {"display_text": display_text})


class DisplayMaskingServer:
    def __init__(self, host: str, port: int, pipeline: MaskingPipeline) -> None:
        self._server = _Server((host, port), _Handler)
        self._server.pipeline = pipeline
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="display-masking-api",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
