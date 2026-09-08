from __future__ import annotations

import json
import unittest
from urllib.parse import urlparse

from security_sink.common import validate_masking_safety
from security_sink.loki_verification import verify_loki_runtime
from security_sink.resilience import FailureDetails, FailureRepository


NOW_NS = 1_788_800_000_000_000_000


def valid_log_line() -> str:
    return json.dumps(
        {
            "event_id": "evt-001",
            "request_id": "req-001",
            "masking_policy_version": "masking-1.0",
            "masked_message": "email=[EMAIL], phone=[PHONE_NUMBER]",
            "body_hash": "a" * 64,
            "safe_metadata": {"route": "/api/saju/chat", "method": "POST"},
        }
    )


def runtime_fetch(
    url: str,
    _timeout: float,
    *,
    line: str | None = None,
    retention: str = "720h",
) -> str:
    path = urlparse(url).path
    if path == "/ready":
        return "ready\n"
    if path == "/config":
        return f"limits_config:\n  retention_period: {retention}\ncompactor:\n  retention_enabled: true\n"
    if path == "/loki/api/v1/query_range":
        values = [] if line is None else [[str(NOW_NS), line]]
        return json.dumps(
            {
                "status": "success",
                "data": {
                    "resultType": "streams",
                    "result": [
                        {
                            "stream": {
                                "pipeline": "security-masked-logs",
                                "data_class": "masked",
                            },
                            "values": values,
                        }
                    ],
                },
            }
        )
    raise AssertionError(f"unexpected URL: {url}")


class SensitiveDataSafetyTests(unittest.TestCase):
    def test_all_required_sensitive_categories_are_rejected(self) -> None:
        samples = {
            "resident_id": "주민번호 900101-1234567",
            "phone": "전화 010-1234-5678",
            "email": "메일 user@example.com",
            "card": "카드 4111 1111 1111 1111",
            "api_key": "api_key=sk-sensitive1234",
            "cloud_key": "key AKIA1234567890ABCDEF",
            "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature123",
            "authorization": "Authorization: Bearer secret-token-value",
            "private_url": "http://192.168.10.20:8080/admin",
            "tailscale_url": "http://100.104.124.29:3306/private",
            "service_url": "http://kafka:9092/topics",
            "internal_domain": "http://loki.internal/ready",
        }
        for category, sample in samples.items():
            with self.subTest(category=category):
                with self.assertRaisesRegex(ValueError, "unmasked sensitive"):
                    validate_masking_safety(sample)

    def test_mask_tokens_and_public_urls_are_allowed(self) -> None:
        validate_masking_safety(
            "email=[EMAIL] phone=[PHONE_NUMBER] authorization=[AUTHORIZATION]",
            {"upstream": "https://api.deepseek.com/v1", "route": "/api/saju/chat"},
        )

    def test_sensitive_error_message_is_rejected_before_db(self) -> None:
        opened = False

        def factory():
            nonlocal opened
            opened = True
            raise AssertionError("DB must not be opened")

        repository = FailureRepository(factory)
        with self.assertRaisesRegex(ValueError, "unmasked sensitive"):
            repository.record(
                object(),  # type: ignore[arg-type]
                event_id="evt-001",
                payload_hash="a" * 64,
                details=FailureDetails(
                    "sink_processing",
                    "TEST",
                    "Authorization: Bearer leaked-secret-token",
                    False,
                ),
                retry_count=1,
                status="RETRYING",
            )
        self.assertFalse(opened)


class LokiRuntimeVerificationTests(unittest.TestCase):
    def test_masked_logs_and_30_day_retention_pass(self) -> None:
        result = verify_loki_runtime(
            "http://127.0.0.1:3100",
            now_ns=NOW_NS,
            fetch_text=lambda url, timeout: runtime_fetch(
                url, timeout, line=valid_log_line()
            ),
        )

        self.assertEqual(result.log_count, 1)
        self.assertEqual(result.retention_hours, 720)

    def test_unmasked_loki_content_fails_verification(self) -> None:
        unsafe = json.loads(valid_log_line())
        unsafe["safe_metadata"] = {"db": "http://100.104.124.29:3306"}
        with self.assertRaisesRegex(ValueError, "unmasked sensitive"):
            verify_loki_runtime(
                "http://127.0.0.1:3100",
                now_ns=NOW_NS,
                fetch_text=lambda url, timeout: runtime_fetch(
                    url, timeout, line=json.dumps(unsafe)
                ),
            )

    def test_empty_loki_result_requires_explicit_allow_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "No completed masked"):
            verify_loki_runtime(
                "http://127.0.0.1:3100",
                now_ns=NOW_NS,
                fetch_text=runtime_fetch,
            )
        result = verify_loki_runtime(
            "http://127.0.0.1:3100",
            now_ns=NOW_NS,
            require_logs=False,
            fetch_text=runtime_fetch,
        )
        self.assertEqual(result.log_count, 0)

    def test_wrong_retention_fails_before_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "720h"):
            verify_loki_runtime(
                "http://127.0.0.1:3100",
                now_ns=NOW_NS,
                fetch_text=lambda url, timeout: runtime_fetch(
                    url, timeout, retention="168h"
                ),
            )


if __name__ == "__main__":
    unittest.main()
