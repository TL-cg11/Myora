from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "security-monitoring" / "ids_shipper" / "ids_loki_shipper.py"
SPEC = importlib.util.spec_from_file_location("ids_loki_shipper", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
IdsLokiShipper = MODULE.IdsLokiShipper
Metrics = MODULE.Metrics
Settings = MODULE.Settings


def event() -> dict:
    return {
        "schema_version": "1.0", "event_id": "ids-event-1",
        "observed_at": "2026-09-14T00:00:00Z", "sensor": "luck-nginx",
        "event_family": "ids_alert", "attack_type": "icmp_flood", "is_ddos": True,
        "severity": "high", "signature": "LUCK DDOS ICMP flood",
        "src_ip": "[REDACTED_IP]", "dest_ip": "[REDACTED_IP]",
    }


class IdsLokiShipperTests(unittest.TestCase):
    def settings(self, root: Path, *, maximum: int = 1_000_000) -> Settings:
        return Settings(
            log_path=root / "ids-events.jsonl", buffer_dir=root / "buffer",
            positions_file=root / "state" / "positions.json",
            quarantine_file=root / "state" / "quarantine.jsonl",
            loki_url="http://127.0.0.1:3100", buffer_max_bytes=maximum,
        )

    def test_persists_before_retrying_and_replays_after_loki_recovers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, settings = Path(temporary), self.settings(Path(temporary))
            settings.log_path.write_text(json.dumps(event()) + "\n", encoding="utf-8")
            failed = IdsLokiShipper(settings, push=lambda *_args: (_ for _ in ()).throw(OSError("down")))
            failed.run_once()
            self.assertEqual(len(list(settings.buffer_dir.glob("*.json"))), 1)
            self.assertEqual(failed.metrics.retries_total, 1)

            sent: list[dict] = []
            recovered = IdsLokiShipper(settings, push=lambda _url, payload: sent.append(json.loads(payload)))
            recovered.run_once()
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["streams"][0]["stream"], {"job": "luck-suricata-ids", "sensor": "luck-nginx"})
            self.assertFalse(list(settings.buffer_dir.glob("*.json")))
            self.assertGreater(recovered.metrics.last_success_unixtime, 0)

    def test_invalid_json_is_quarantined_without_stopping_following_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self.settings(Path(temporary))
            settings.log_path.write_text("not-json\n" + json.dumps(event()) + "\n", encoding="utf-8")
            shipper = IdsLokiShipper(settings, push=lambda *_args: None)
            shipper.run_once()
            self.assertEqual(shipper.metrics.parse_errors_total, 1)
            self.assertEqual(shipper.metrics.sent_total, 1)
            self.assertIn("INVALID_IDS_JSONL", settings.quarantine_file.read_text(encoding="utf-8"))

    def test_buffer_limit_records_loss_without_leaking_source_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self.settings(Path(temporary), maximum=1)
            settings.log_path.write_text(json.dumps(event()) + "\n", encoding="utf-8")
            metrics = Metrics()
            shipper = IdsLokiShipper(settings, metrics, push=lambda *_args: None)
            shipper.run_once()
            self.assertEqual(metrics.lost_total, 1)
            self.assertEqual(metrics.sent_total, 0)
            rendered = metrics.render().decode()
            self.assertIn("luck_ids_shipper_buffer_limit_bytes 1", rendered)
            self.assertNotIn("ids-event-1", rendered)

    def test_allowlist_excludes_unexpected_raw_eve_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self.settings(Path(temporary))
            record = event() | {"suricata_event": {"src_ip": "198.51.100.42"}}
            settings.log_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            sent: list[dict] = []
            IdsLokiShipper(settings, push=lambda _url, payload: sent.append(json.loads(payload))).run_once()
            line = sent[0]["streams"][0]["values"][0][1]
            self.assertNotIn("suricata_event", line)
            self.assertNotIn("198.51.100.42", line)


if __name__ == "__main__":
    unittest.main()
