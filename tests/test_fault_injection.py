from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from security_sink.common import KafkaMetadata
from security_sink.fault_injection import crash_once


class FaultInjectionTests(unittest.TestCase):
    def test_marker_is_payload_free_and_crash_happens_only_once(self) -> None:
        metadata = KafkaMetadata("masked-log-sink", "myohan.masked-logs", 0, 42, "secret-key")
        exits: list[int] = []
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "checkpoint.json"
            with patch.dict(os.environ, {"TEST_CRASH_MARKER": str(marker)}):
                crash_once("TEST_CRASH_MARKER", "after_loki", metadata, terminate=exits.append)
                crash_once("TEST_CRASH_MARKER", "after_loki", metadata, terminate=exits.append)

            payload = json.loads(marker.read_text(encoding="utf-8"))

        self.assertEqual(exits, [137])
        self.assertEqual(payload["checkpoint"], "after_loki")
        self.assertEqual(payload["offset"], 42)
        self.assertNotIn("secret-key", marker.name)
        self.assertNotIn("key", payload)


if __name__ == "__main__":
    unittest.main()
