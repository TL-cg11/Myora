import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run-saju-security-integration-test.sh"


class SajuSecurityIntegrationScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")

    def test_defines_balanced_medium_high_and_combined_scenarios(self) -> None:
        for scenario in (
            "normal_saju_chat",
            "medium_prompt_injection",
            "medium_phone_number",
            "medium_combined",
            "high_rrn",
            "high_api_key",
            "high_combined",
        ):
            self.assertIn(f'"{scenario}"', self.source)
        for rule in (
            "PROMPT_INJECTION",
            "PHONE_NUMBER",
            "EMAIL_ADDRESS",
            "KR_RRN",
            "API_KEY",
        ):
            self.assertIn(rule, self.source)

    def test_remains_safe_by_default(self) -> None:
        self.assertIn('if [[ "$EXECUTE" != true ]]', self.source)
        self.assertIn('"fault_injection": False', self.source)
        self.assertIn("DLQ and Flood fault injection are deliberately outside", self.source)
        self.assertIn("synthetic_data_only", self.source)
        self.assertIn('PYTHON_BIN="${PYTHON_BIN:-python3}"', self.source)

    def test_splits_requests_across_readings(self) -> None:
        self.assertIn("if ((index % 4 == 0))", self.source)
        self.assertIn('"chat_rows_created": 7', self.source)
        self.assertIn('"reading_ids"', self.source)

    @unittest.skipIf(os.name == "nt" or shutil.which("bash") is None, "POSIX bash is unavailable")
    def test_bash_syntax(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
