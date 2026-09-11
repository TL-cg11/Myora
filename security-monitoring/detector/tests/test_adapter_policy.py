# 정책 로딩과 필드 단위 변환이 정책 파일과 일치하는지 검사한다.
import json
from pathlib import Path
import tempfile
import unittest

from adapter.config import ConfigError, load_settings
from adapter.normalize import (AdapterError, normalize_environment, safe_identity,
                               to_utc_z)
from adapter.policy import PolicyError, load_policy, mask_ip, pseudonymize

KEY = b"unit-test-pseudonym-key-0123456789"


class PolicyLoadingTest(unittest.TestCase):
    def test_ships_with_the_was_log_masking_policy(self):
        policy = load_policy()
        self.assertEqual(policy.policy_version, "1.0")
        self.assertEqual(policy.schema_version, "1.0")
        self.assertEqual(policy.action_for("user_id"), "pseudonymize")
        self.assertEqual(policy.action_for("client_ip"), "mask_ip")
        self.assertEqual(policy.action_for("input.question"), "detect_and_mask")
        self.assertEqual(policy.action_for("input.topic"), "pass")
        self.assertTrue(policy.prompt_injection_enabled("input.question"))
        self.assertFalse(policy.prompt_injection_enabled("input.topic"))

    def test_unknown_input_field_follows_the_default_rule(self):
        policy = load_policy()
        self.assertEqual(policy.action_for("input.nickname"), "reject")
        self.assertEqual(policy.action_for("method"), "pass")

    def test_unsupported_action_stops_startup(self):
        document = {"policy_version": "9.9", "schema_version": "1.0",
                    "fields": {"user_id": {"action": "encrypt"}}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "policy.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(PolicyError):
                load_policy(path)


class ValueMaskingTest(unittest.TestCase):
    def test_pseudonym_is_stable_and_field_scoped(self):
        first = pseudonymize(42, KEY, "user_id")
        self.assertEqual(first, pseudonymize(42, KEY, "user_id"))
        self.assertNotEqual(first, pseudonymize(42, KEY, "guest_key"))
        self.assertNotEqual(first, pseudonymize(42, b"another-key-" + KEY, "user_id"))
        self.assertNotIn("42", first)

    def test_ip_masking_keeps_only_the_network_part(self):
        self.assertEqual(mask_ip("100.10.20.30"), "100.10.20.0")
        self.assertEqual(mask_ip("2001:db8:1234:5678::1"), "2001:db8:1234::")
        self.assertEqual(mask_ip("unknown"), "[REDACTED_IP]")
        self.assertEqual(mask_ip(None), "[REDACTED_IP]")


class NormalizationHelperTest(unittest.TestCase):
    def test_identity_fields_keep_only_allowed_characters(self):
        self.assertEqual(safe_identity("req 001!", 64), "req-001-")
        self.assertEqual(safe_identity("x" * 100, 64), "x" * 64)
        self.assertIsNone(safe_identity("!!!", 64))
        self.assertIsNone(safe_identity(None, 64))

    def test_environment_aliases_match_the_consumer_contract(self):
        self.assertEqual(normalize_environment("PROD", "development"), "production")
        self.assertEqual(normalize_environment(None, "staging"), "staging")
        with self.assertRaises(AdapterError):
            normalize_environment("sandbox", "development")

    def test_timestamps_become_utc_with_a_z_suffix(self):
        self.assertEqual(to_utc_z("2026-09-08T13:20:00+09:00"), "2026-09-08T04:20:00.000Z")
        self.assertEqual(to_utc_z("2026-09-08T04:20:00Z"), "2026-09-08T04:20:00.000Z")
        self.assertTrue(to_utc_z(1757304000).endswith("Z"))
        with self.assertRaises(AdapterError):
            to_utc_z("어제")


class SettingsTest(unittest.TestCase):
    def test_short_pseudonym_key_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_settings({"MASKING_PSEUDONYM_KEY": "too-short"})

    def test_missing_pseudonym_key_is_rejected(self):
        with self.assertRaises(ConfigError):
            load_settings({})

    def test_defaults_cover_the_current_topic_names(self):
        settings = load_settings({"MASKING_PSEUDONYM_KEY": KEY.decode("utf-8")})
        self.assertEqual(
            settings.input_topics, ("myohan.was.app", "myohan.nginx.access")
        )
        self.assertEqual(settings.masked_logs_topic, "myohan.masked-logs")
        self.assertEqual(settings.security_events_topic, "myohan.security-events")
        self.assertFalse(settings.consumer_config()["enable.auto.commit"])
        self.assertTrue(settings.producer_config()["enable.idempotence"])
        self.assertFalse(settings.ner_enabled)
        self.assertEqual(settings.ner_threshold, 0.85)
        self.assertFalse(settings.pii_context_enabled)
        self.assertEqual(settings.pii_context_non_pii_threshold, 0.90)
        self.assertEqual(
            settings.pii_context_model, "Huffon/klue-roberta-base-nli"
        )

    def test_ner_settings_are_validated(self):
        base = {"MASKING_PSEUDONYM_KEY": KEY.decode("utf-8")}
        settings = load_settings({**base, "DETECTOR_NER_ENABLED": "true",
                                  "DETECTOR_NER_THRESHOLD": "0.9",
                                  "DETECTOR_NER_LOCAL_FILES_ONLY": "yes"})
        self.assertTrue(settings.ner_enabled)
        self.assertTrue(settings.ner_local_files_only)
        self.assertEqual(settings.ner_threshold, 0.9)
        with self.assertRaises(ConfigError):
            load_settings({**base, "DETECTOR_NER_THRESHOLD": "1.1"})
        with self.assertRaises(ConfigError):
            load_settings({**base, "DETECTOR_NER_THRESHOLD": "high"})
        with self.assertRaises(ConfigError):
            load_settings({**base, "DETECTOR_NER_ENABLED": "sometimes"})

    def test_pii_context_settings_are_validated(self):
        base = {"MASKING_PSEUDONYM_KEY": KEY.decode("utf-8")}
        settings = load_settings({
            **base,
            "DETECTOR_PII_CONTEXT_ENABLED": "true",
            "DETECTOR_PII_CONTEXT_NON_PII_THRESHOLD": "0.95",
            "DETECTOR_PII_CONTEXT_LOCAL_FILES_ONLY": "yes",
        })
        self.assertTrue(settings.pii_context_enabled)
        self.assertTrue(settings.pii_context_local_files_only)
        self.assertEqual(settings.pii_context_non_pii_threshold, 0.95)
        with self.assertRaises(ConfigError):
            load_settings({
                **base, "DETECTOR_PII_CONTEXT_NON_PII_THRESHOLD": "0.49"
            })


if __name__ == "__main__":
    unittest.main()
