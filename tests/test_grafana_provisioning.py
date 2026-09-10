import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAFANA = ROOT / "observability" / "grafana"


class GrafanaProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = json.loads((GRAFANA / "dashboards" / "security-events.json").read_text())
        cls.consumers = json.loads((GRAFANA / "dashboards" / "security-consumers.json").read_text())
        cls.datasources = (GRAFANA / "provisioning" / "datasources" / "datasources.yml").read_text()
        cls.alerts = (GRAFANA / "provisioning" / "alerting" / "security-consumer-alerts.yml").read_text()
        cls.installer = (ROOT / "scripts" / "observability-install.sh").read_text()

    def test_datasources_have_stable_uids_and_no_database_secret(self):
        for uid in ("prometheus", "loki", "security-monitoring-mysql"):
            self.assertIn(f"uid: {uid}", self.datasources)
        self.assertIn("${GRAFANA_SECURITY_DB_PASSWORD}", self.datasources)
        self.assertNotIn("replace-with-the-readonly-db-password", self.datasources)

    def test_event_dashboard_covers_planned_views(self):
        titles = {panel["title"] for panel in self.events["panels"]}
        self.assertEqual(
            titles,
            {
                "Events by risk level", "Detections by category", "Top entity types",
                "Top detection rules", "Events by status", "Security events over time",
                "Untreated / long-unresolved events",
            },
        )
        sql = "\n".join(target["rawSql"] for panel in self.events["panels"] for target in panel["targets"])
        for field in ("risk_level", "category", "entity_type", "rule_id", "status", "detected_at"):
            self.assertIn(field, sql)
        self.assertIn("${unresolved_hours:raw}", sql)
        self.assertNotIn("INSERT ", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())

    def test_consumer_dashboard_covers_metrics_and_masked_logs(self):
        payload = json.dumps(self.consumers)
        for metric in (
            "luck_consumer_lag_messages", "luck_sink_messages_total",
            "luck_sink_processing_duration_seconds_bucket", "luck_sink_failures_total",
            "luck_sink_retries_total", "luck_sink_dlq_total",
        ):
            self.assertIn(metric, payload)
        self.assertIn('{pipeline=\\"security-masked-logs\\", data_class=\\"masked\\"} | json', payload)

    def test_alerts_cover_lag_dlq_and_target_failure(self):
        for uid in (
            "luck-security-lag-high", "luck-security-lag-critical",
            "luck-security-message-stale", "luck-security-dlq-detected",
            "luck-security-sink-down",
        ):
            self.assertIn(f"uid: {uid}", self.alerts)
        self.assertIn("luck_consumer_lag_messages", self.alerts)
        self.assertIn("luck_sink_dlq_total", self.alerts)
        self.assertIn('up{job="luck-security-sinks"}', self.alerts)
        self.assertIn("contactPoints:", self.alerts)
        self.assertIn("Luck Security Operations", self.alerts)
        self.assertIn("uid: luck-security-discord", self.alerts)
        self.assertIn("type: discord", self.alerts)
        self.assertIn("$GRAFANA_DISCORD_WEBHOOK_URL", self.alerts)
        self.assertNotIn("type: slack", self.alerts)
        self.assertNotIn("type: email", self.alerts)
        self.assertIn("group_wait: 30s", self.alerts)
        self.assertIn("repeat_interval: 4h", self.alerts)

    def test_installer_provisions_all_grafana_assets(self):
        for path in (
            "/etc/grafana/provisioning/datasources",
            "/etc/grafana/provisioning/dashboards",
            "/etc/grafana/provisioning/alerting",
            "/var/lib/grafana/dashboards/security-monitoring",
        ):
            self.assertIn(path, self.installer)
        runtime_test = (ROOT / "scripts" / "observability-test.sh").read_text()
        for uid in (
            "security-monitoring-mysql", "luck-security-events",
            "luck-security-consumers", "luck-security-lag-high",
            "luck-security-lag-critical", "luck-security-message-stale",
            "luck-security-dlq-detected", "luck-security-sink-down",
        ):
            self.assertIn(uid, runtime_test)


if __name__ == "__main__":
    unittest.main()
