from __future__ import annotations

import unittest
from pathlib import Path


class Part13RetentionVerificationTests(unittest.TestCase):
    def test_verifier_requires_explicit_execute(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts/verify_part13_retention.py").read_text()
        self.assertIn('parser.add_argument(\n        "--execute"', script)
        self.assertIn("dry_run=True", script)
        self.assertIn("dry_run=False", script)
        self.assertIn('timer == {"enabled": "enabled", "active": "active"}', script)
        self.assertIn('report["status"] = "ok" if passed else "failed"', script)


if __name__ == "__main__":
    unittest.main()
