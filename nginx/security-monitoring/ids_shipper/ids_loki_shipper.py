#!/usr/bin/env python3
"""Durable JSONL shipper for classified Suricata IDS alerts.

The shipper reads only the classifier's normalized JSONL output, keeps source
IP and event IDs in the Loki JSON body (never labels), and persists every valid
line to a local buffer before attempting a Loki push.
"""

from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Settings:
    log_path: Path
    buffer_dir: Path
    positions_file: Path
    quarantine_file: Path
    loki_url: str
    buffer_max_bytes: int = 64 * 1024 * 1024
    poll_seconds: float = 1.0


@dataclass
class Metrics:
    lines_read_total: int = 0
    parse_errors_total: int = 0
    buffered_total: int = 0
    sent_total: int = 0
    retries_total: int = 0
    lost_total: int = 0
    buffer_bytes: int = 0
    buffer_limit_bytes: int = 0
    last_success_unixtime: float = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def render(self) -> bytes:
        with self.lock:
            values = {
                "luck_ids_shipper_lines_read_total": self.lines_read_total,
                "luck_ids_shipper_parse_errors_total": self.parse_errors_total,
                "luck_ids_shipper_buffered_total": self.buffered_total,
                "luck_ids_shipper_sent_total": self.sent_total,
                "luck_ids_shipper_retries_total": self.retries_total,
                "luck_ids_shipper_lost_total": self.lost_total,
                "luck_ids_shipper_buffer_bytes": self.buffer_bytes,
                "luck_ids_shipper_buffer_limit_bytes": self.buffer_limit_bytes,
                "luck_ids_shipper_last_loki_success_unixtime": self.last_success_unixtime,
            }
        return "".join(f"{name} {value}\n" for name, value in values.items()).encode()


class IdsLokiShipper:
    def __init__(
        self, settings: Settings, metrics: Metrics | None = None,
        push: Callable[[str, bytes], None] | None = None,
    ) -> None:
        self.settings, self.metrics = settings, metrics or Metrics()
        self._push = push or self._http_push
        self._sequence = 0
        self.settings.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.settings.positions_file.parent.mkdir(parents=True, exist_ok=True)
        self.settings.quarantine_file.parent.mkdir(parents=True, exist_ok=True)
        self.metrics.buffer_bytes = self._buffer_size()
        self.metrics.buffer_limit_bytes = settings.buffer_max_bytes

    def run_once(self) -> None:
        self._read_new_lines()
        self.flush_buffer()

    def _read_new_lines(self) -> None:
        try:
            stat = self.settings.log_path.stat()
        except FileNotFoundError:
            return
        state = self._load_position()
        offset = state.get("offset", 0) if state.get("inode") == stat.st_ino else 0
        if not isinstance(offset, int) or offset < 0 or offset > stat.st_size:
            offset = 0
        with self.settings.log_path.open("r", encoding="utf-8", errors="replace") as source:
            source.seek(offset)
            while line := source.readline():
                self.metrics.lines_read_total += 1
                self._handle_line(line)
                self._save_position(stat.st_ino, source.tell())

    def _handle_line(self, line: str) -> None:
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError("IDS JSONL record must be an object")
        except (ValueError, json.JSONDecodeError):
            self.metrics.parse_errors_total += 1
            with self.settings.quarantine_file.open("a", encoding="utf-8") as target:
                target.write(json.dumps({"error": "INVALID_IDS_JSONL"}, separators=(",", ":")) + "\n")
            return
        self._buffer_event(event)

    def _buffer_event(self, event: dict[str, Any]) -> None:
        # The classifier contract is explicitly allow-listed: do not relay an
        # accidentally added raw EVE object or an unmasked address to Loki.
        allowed = (
            "schema_version", "event_id", "observed_at", "sensor", "event_family",
            "attack_type", "is_ddos", "severity", "signature", "signature_id",
            "category", "action", "src_ip", "src_port", "dest_ip", "dest_port",
            "proto", "flow_id",
        )
        payload = json.dumps({key: event[key] for key in allowed if key in event},
                             ensure_ascii=False, separators=(",", ":"))
        encoded = payload.encode("utf-8")
        if self._buffer_size() + len(encoded) > self.settings.buffer_max_bytes:
            self.metrics.lost_total += 1
            return
        self._sequence += 1
        path = self.settings.buffer_dir / f"{time.time_ns():020d}-{self._sequence:06d}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, path)
        self.metrics.buffered_total += 1
        self.metrics.buffer_bytes = self._buffer_size()

    def flush_buffer(self) -> None:
        for path in sorted(self.settings.buffer_dir.glob("*.json")):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
                self._push(self.settings.loki_url, self._loki_payload(event))
            except (OSError, ValueError, HTTPError, URLError):
                self.metrics.retries_total += 1
                break
            path.unlink()
            self.metrics.sent_total += 1
            self.metrics.last_success_unixtime = time.time()
        self.metrics.buffer_bytes = self._buffer_size()

    @staticmethod
    def _loki_payload(event: dict[str, Any]) -> bytes:
        timestamp = event.get("observed_at")
        try:
            instant = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            nanoseconds = int(instant.astimezone(timezone.utc).timestamp() * 1_000_000_000)
        except (TypeError, ValueError, OverflowError):
            nanoseconds = time.time_ns()
        return json.dumps({
            "streams": [{
                "stream": {"job": "luck-suricata-ids", "sensor": "luck-nginx"},
                "values": [[str(nanoseconds), json.dumps(event, ensure_ascii=False, separators=(",", ":"))]],
            }]
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @staticmethod
    def _http_push(url: str, payload: bytes) -> None:
        request = Request(url.rstrip("/") + "/loki/api/v1/push", data=payload,
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=10) as response:
            if not 200 <= response.status < 300:
                raise OSError("Loki returned a non-success status")

    def _buffer_size(self) -> int:
        return sum(path.stat().st_size for path in self.settings.buffer_dir.glob("*.json"))

    def _load_position(self) -> dict[str, int]:
        try:
            value = json.loads(self.settings.positions_file.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    def _save_position(self, inode: int, offset: int) -> None:
        temporary = self.settings.positions_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"inode": inode, "offset": offset}) + "\n", encoding="utf-8")
        os.replace(temporary, self.settings.positions_file)


def _settings_from_environment() -> Settings:
    root = Path("/var/lib/luck-security/ids-loki")
    return Settings(
        log_path=Path(os.getenv("IDS_LOG_PATH", "/var/log/luck-security/ids-events.jsonl")),
        buffer_dir=Path(os.getenv("IDS_BUFFER_DIR", str(root / "buffer"))),
        positions_file=Path(os.getenv("IDS_POSITIONS_FILE", str(root / "positions.json"))),
        quarantine_file=Path(os.getenv("IDS_QUARANTINE_FILE", str(root / "quarantine.jsonl"))),
        loki_url=os.getenv("IDS_LOKI_URL", "http://127.0.0.1:3100"),
        buffer_max_bytes=int(os.getenv("IDS_BUFFER_MAX_BYTES", str(64 * 1024 * 1024))),
        poll_seconds=float(os.getenv("IDS_POLL_SECONDS", "1")),
    )


def serve_metrics(metrics: Metrics, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path != "/metrics":
                self.send_error(404)
                return
            body = metrics.render()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args: Any) -> None:
            return
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings, metrics = _settings_from_environment(), Metrics()
    shipper = IdsLokiShipper(settings, metrics)
    server = serve_metrics(metrics, int(os.getenv("IDS_METRICS_PORT", "9110")))
    try:
        while True:
            shipper.run_once()
            if args.once:
                return 0
            time.sleep(settings.poll_seconds)
    finally:
        server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
