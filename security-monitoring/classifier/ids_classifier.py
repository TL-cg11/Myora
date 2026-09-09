#!/usr/bin/env python3
"""Tail Suricata EVE alerts and write a normalized, classified JSONL stream."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, TextIO


DEFAULT_INPUT = Path("/var/log/suricata/eve.json")
DEFAULT_OUTPUT = Path("/var/log/luck-security/ids-events.jsonl")
DEFAULT_STATE = Path("/var/lib/luck-security/ids-classifier.offset")


def classify(event: dict[str, Any]) -> dict[str, Any] | None:
    if event.get("event_type") != "alert":
        return None

    alert = event.get("alert") if isinstance(event.get("alert"), dict) else {}
    signature = str(alert.get("signature", "unknown"))
    category = str(alert.get("category", "unknown"))
    signature_lower = signature.lower()
    category_lower = category.lower()

    attack_type = "community_alert"
    is_ddos = False
    if "tcp syn flood" in signature_lower:
        attack_type, is_ddos = "tcp_syn_flood", True
    elif "udp flood" in signature_lower:
        attack_type, is_ddos = "udp_flood", True
    elif "icmp flood" in signature_lower:
        attack_type, is_ddos = "icmp_flood", True
    elif "web connection flood" in signature_lower:
        attack_type, is_ddos = "web_connection_flood", True
    elif "denial of service" in category_lower:
        attack_type, is_ddos = "community_dos", True

    try:
        numeric_severity = int(alert.get("severity", 3))
    except (TypeError, ValueError):
        numeric_severity = 3
    severity = "critical" if numeric_severity <= 1 else "high" if numeric_severity == 2 else "medium"

    return {
        "schema_version": "1.0",
        "event_id": str(uuid.uuid4()),
        "observed_at": event.get("timestamp"),
        "sensor": "luck-nginx",
        "event_family": "ids_alert",
        "attack_type": attack_type,
        "is_ddos": is_ddos,
        "severity": severity,
        "signature": signature,
        "signature_id": alert.get("signature_id"),
        "category": category,
        "action": alert.get("action", "allowed"),
        "src_ip": event.get("src_ip"),
        "src_port": event.get("src_port"),
        "dest_ip": event.get("dest_ip"),
        "dest_port": event.get("dest_port"),
        "proto": event.get("proto"),
        "flow_id": event.get("flow_id"),
        "suricata_event": event,
    }


def emit_classified(source: TextIO, destination: TextIO) -> int:
    emitted = 0
    for line in source:
        try:
            event = json.loads(line)
            normalized = classify(event)
        except (json.JSONDecodeError, TypeError):
            continue
        if normalized is not None:
            destination.write(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n")
            destination.flush()
            emitted += 1
    return emitted


def load_state(path: Path) -> tuple[int | None, int]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return int(state["inode"]), int(state["offset"])
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None, 0


def save_state(path: Path, inode: int, offset: int) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"inode": inode, "offset": offset}) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def follow(source_path: Path, output_path: Path, state_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    saved_inode, saved_offset = load_state(state_path)

    while True:
        try:
            stat = source_path.stat()
        except FileNotFoundError:
            time.sleep(1)
            continue

        offset = saved_offset if saved_inode == stat.st_ino and saved_offset <= stat.st_size else 0
        with source_path.open("r", encoding="utf-8", errors="replace") as source, output_path.open(
            "a", encoding="utf-8"
        ) as destination:
            source.seek(offset)
            while True:
                line = source.readline()
                if line:
                    emit_classified(iter((line,)), destination)
                    save_state(state_path, stat.st_ino, source.tell())
                    continue

                time.sleep(0.5)
                try:
                    current = source_path.stat()
                except FileNotFoundError:
                    break
                if current.st_ino != stat.st_ino or current.st_size < source.tell():
                    break

        saved_inode, saved_offset = None, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classify-stdin", action="store_true")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()

    if args.classify_stdin:
        emit_classified(sys.stdin, sys.stdout)
        return 0
    follow(args.input, args.output, args.state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
