from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "security-monitoring" / "classifier" / "ids_classifier.py"
SPEC = importlib.util.spec_from_file_location("ids_classifier", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class IdsClassifierTests(unittest.TestCase):
    def test_classifier_masks_addresses_and_omits_raw_eve(self):
        record = MODULE.classify({
            "event_type": "alert", "timestamp": "2026-09-14T00:00:00.000000+0000",
            "src_ip": "198.51.100.42", "dest_ip": "2001:db8:1:2::9",
            "alert": {"signature": "LUCK DDOS ICMP flood", "category": "Denial of Service", "severity": 2},
        })
        assert record is not None
        self.assertEqual(record["src_ip"], "198.51.100.0/24")
        self.assertEqual(record["dest_ip"], "2001:db8:1::/48")
        self.assertNotIn("suricata_event", record)


if __name__ == "__main__":
    unittest.main()
