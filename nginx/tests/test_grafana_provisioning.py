import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GRAFANA = ROOT / "observability" / "grafana"


class GrafanaProvisioningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = json.loads(
            (GRAFANA / "dashboards" / "security-events.json").read_text(encoding="utf-8")
        )
        cls.consumers = json.loads(
            (GRAFANA / "dashboards" / "security-consumers.json").read_text(encoding="utf-8")
        )
        cls.ids = json.loads(
            (GRAFANA / "dashboards" / "suricata-ids.json").read_text(encoding="utf-8")
        )
        cls.ids_shipper = json.loads(
            (GRAFANA / "dashboards" / "ids-shipper.json").read_text(encoding="utf-8")
        )
        cls.datasources = (GRAFANA / "provisioning" / "datasources" / "datasources.yml").read_text()
        cls.alerts = (
            GRAFANA / "provisioning" / "alerting" / "security-consumer-alerts.yml"
        ).read_text(encoding="utf-8")
        cls.installer = (ROOT / "scripts" / "observability-install.sh").read_text()
        cls.nginx = (ROOT / "conf.d" / "luck.conf").read_text()
        cls.grafana_ini = (GRAFANA / "grafana.ini").read_text()
        cls.part14_runner = (ROOT / "scripts" / "run-part14-dashboard.sh").read_text()

    def test_datasources_have_stable_uids_and_no_database_secret(self):
        for uid in ("prometheus", "loki", "security-monitoring-mysql"):
            self.assertIn(f"uid: {uid}", self.datasources)
        self.assertIn("${GRAFANA_SECURITY_DB_PASSWORD}", self.datasources)
        self.assertNotIn("replace-with-the-readonly-db-password", self.datasources)

    def test_event_dashboard_covers_planned_views(self):
        titles = {panel["title"] for panel in self.events["panels"]}
        self.assertTrue(
            {
                "Events by risk level", "Detections by category", "Top entity types",
                "Top detection rules", "Events by status", "Security events over time",
                "Untreated / long-unresolved events",
            }.issubset(titles),
        )
        sql = "\n".join(
            target["rawSql"] for panel in self.events["panels"]
            for target in panel["targets"] if "rawSql" in target
        )
        for field in ("risk_level", "category", "entity_type", "rule_id", "status", "detected_at"):
            self.assertIn(field, sql)
        self.assertIn("${unresolved_hours:raw}", sql)
        self.assertNotIn("INSERT ", sql.upper())
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())
        event_payload = json.dumps(self.events)
        self.assertNotIn("luck-suricata-ids", event_payload)
        self.assertNotIn("Recent Suricata IDS alerts", titles)

    def test_event_risk_panels_use_semantic_fixed_colors(self):
        expected = {
            "CRITICAL": "red",
            "HIGH": "orange",
            "MEDIUM": "yellow",
            "LOW": "green",
        }

        for title in ("Events by risk level", "Security events over time"):
            panel = next(
                panel for panel in self.events["panels"] if panel["title"] == title
            )
            actual = {}
            for override in panel["fieldConfig"]["overrides"]:
                name = override["matcher"]["options"]
                color = next(
                    item["value"]["fixedColor"]
                    for item in override["properties"]
                    if item["id"] == "color"
                )
                actual[name] = color
            self.assertEqual(actual, expected)

        risk_panel = next(
            panel for panel in self.events["panels"]
            if panel["title"] == "Events by risk level"
        )
        sql = risk_panel["targets"][0]["rawSql"]
        for level in expected:
            self.assertIn(f"AS {level}", sql)
        self.assertNotIn("risk_level AS metric", sql)

    def test_event_tables_use_semantic_risk_text_colors(self):
        expected = {
            "CRITICAL": "red",
            "HIGH": "orange",
            "MEDIUM": "yellow",
            "LOW": "green",
        }
        for title in ("Untreated / long-unresolved events", "Event details"):
            panel = next(
                panel for panel in self.events["panels"] if panel["title"] == title
            )
            override = next(
                item for item in panel["fieldConfig"]["overrides"]
                if item["matcher"]["options"] == "risk_level"
            )
            properties = {item["id"]: item["value"] for item in override["properties"]}
            mapping = properties["mappings"][0]["options"]
            self.assertEqual(
                {level: value["color"] for level, value in mapping.items()},
                expected,
            )
            self.assertEqual(
                properties["custom.cellOptions"], {"type": "color-text"}
            )

    def test_consumer_dashboard_covers_metrics_and_masked_logs(self):
        payload = json.dumps(self.consumers)
        for metric in (
            "luck_consumer_lag_messages", "luck_sink_messages_total",
            "luck_sink_processing_duration_seconds_bucket", "luck_sink_failures_total",
            "luck_sink_retries_total", "luck_sink_dlq_total",
        ):
            self.assertIn(metric, payload)
        self.assertIn('{pipeline=\\"security-masked-logs\\", data_class=\\"masked\\", source_type=\\"chat_request\\"} | json', payload)
        masked_panel = next(
            panel for panel in self.consumers["panels"]
            if panel["title"] == "마스킹된 챗봇 요청 · 응답 로그"
        )
        self.assertNotIn("| limit", json.dumps(masked_panel))
        self.assertEqual([target["maxLines"] for target in masked_panel["targets"]], [100, 100])
        self.assertIn('masked_message != \\"\\"', json.dumps(masked_panel))
        self.assertIn('source_type=\\"chat_request\\"', json.dumps(masked_panel))
        self.assertIn('source_type=\\"chat_response\\"', json.dumps(masked_panel))
        self.assertIn("REQUEST · 사용자", json.dumps(masked_panel, ensure_ascii=False))
        self.assertIn("RESPONSE · AI", json.dumps(masked_panel, ensure_ascii=False))
        self.assertNotIn(
            "실시간 모니터링 서버 시각",
            {panel["title"] for panel in self.consumers["panels"]},
        )
        self.assertNotIn(
            "Security sink targets",
            {panel["title"] for panel in self.consumers["panels"]},
        )
        self.assertEqual(masked_panel["gridPos"], {"h": 17, "w": 24, "x": 0, "y": 16})
        detail_panel = next(panel for panel in self.events["panels"] if panel["title"] == "Event details")
        self.assertIn("event_id = ${event_id:sqlstring}", detail_panel["targets"][0]["rawSql"])
        self.assertIn("masked_excerpt", detail_panel["targets"][0]["rawSql"])

    def test_ids_dashboards_separate_alert_content_from_shipper_operations(self):
        ids_payload = json.dumps(self.ids)
        operations_payload = json.dumps(self.ids_shipper)
        for field in ("attack_type", "severity", "Recent IDS flood alerts"):
            self.assertIn(field, ids_payload)
        attack_panel = next(panel for panel in self.ids["panels"] if panel["id"] == 1)
        self.assertEqual(
            [target["legendFormat"] for target in attack_panel["targets"]],
            ["TCP SYN Flood", "UDP Flood", "ICMP Flood", "Web Connection Flood"],
        )
        severity_panel = next(panel for panel in self.ids["panels"] if panel["id"] == 2)
        self.assertEqual(
            [target["legendFormat"] for target in severity_panel["targets"]],
            ["CRITICAL", "HIGH", "MEDIUM"],
        )
        severity_colors = {
            override["matcher"]["options"]: next(
                item["value"]["fixedColor"]
                for item in override["properties"]
                if item["id"] == "color"
            )
            for override in severity_panel["fieldConfig"]["overrides"]
        }
        self.assertEqual(
            severity_colors,
            {
                "CRITICAL": "red",
                "HIGH": "orange",
                "MEDIUM": "yellow",
                "LOW": "green",
            },
        )
        for target in attack_panel["targets"] + severity_panel["targets"]:
            self.assertIn("or on() vector(0)", target["expr"])
            self.assertIn("$__interval", target["expr"])
        self.assertNotIn("community_alert", ids_payload)
        for metric in (
            "luck_ids_shipper_buffer_bytes", "luck_ids_shipper_buffer_limit_bytes",
            "luck_ids_shipper_retries_total", "luck_ids_shipper_lost_total",
            "luck_ids_shipper_last_loki_success_unixtime",
        ):
            self.assertIn(metric, operations_payload)
        self.assertNotIn("discord", ids_payload.lower())

    def test_alerts_cover_lag_dlq_and_target_failure(self):
        for uid in (
            "luck-security-lag-high", "luck-security-lag-critical",
            "luck-security-message-stale", "luck-security-dlq-detected",
            "luck-security-sink-down",
        ):
            self.assertIn(f"uid: {uid}", self.alerts)
        self.assertIn("luck_consumer_lag_messages", self.alerts)
        self.assertIn("luck_sink_dlq_total", self.alerts)
        self.assertIn(
            "luck_sink_dlq_total unless luck_sink_dlq_total offset 5m",
            self.alerts,
        )
        self.assertIn('up{job="luck-security-sinks"}', self.alerts)
        self.assertIn("contactPoints:", self.alerts)
        self.assertIn("Luck Security Operations", self.alerts)
        self.assertIn("uid: luck-security-discord", self.alerts)
        self.assertIn("type: discord", self.alerts)
        self.assertIn("$GRAFANA_DISCORD_WEBHOOK_URL", self.alerts)
        self.assertIn("name: luck-security-operations-message", self.alerts)
        self.assertIn('message: \'{{ template "luck.security.operations.message" . }}\'', self.alerts)
        self.assertIn("Luck 보안 운영 경고", self.alerts)
        self.assertIn("Luck 보안 운영 복구", self.alerts)
        self.assertIn("보안 로그 격리(DLQ) 발생", self.alerts)
        self.assertGreaterEqual(self.alerts.count('{{ "\\n" -}}'), 2)
        self.assertNotIn("type: slack", self.alerts)
        self.assertNotIn("type: email", self.alerts)
        self.assertIn("group_wait: 30s", self.alerts)
        self.assertIn("repeat_interval: 4h", self.alerts)

    def test_suricata_flood_alerts_are_grouped_and_routed_to_korean_discord(self):
        for value in (
            "name: luck-suricata-flood-alerts",
            "interval: 1m",
            "uid: luck-ids-flood-detected",
            "count_over_time",
            'attack_type=~"tcp_syn_flood|udp_flood|icmp_flood|web_connection_flood" [1m]',
            "sum by (attack_type, severity)",
            "keepFiringFor: 2m",
            "name: Luck IDS Flood Alerts",
            "uid: luck-ids-flood-discord",
            "name: luck-ids-flood-message",
            "Luck IDS Flood 공격 알림",
            "최근 1분간",
            "notification_scope: ids-flood",
            "group_by: [alertname, attack_type, severity]",
            "group_interval: 1m",
            "repeat_interval: 10m",
        ):
            self.assertIn(value, self.alerts)

    def test_installer_provisions_all_grafana_assets(self):
        for path in (
            "/etc/grafana/provisioning/datasources",
            "/etc/grafana/provisioning/dashboards",
            "/etc/grafana/provisioning/alerting",
            "/var/lib/grafana/dashboards/security-monitoring",
            "/etc/prometheus/ids-shipper-targets.yml",
        ):
            self.assertIn(path, self.installer)
        runtime_test = (ROOT / "scripts" / "observability-test.sh").read_text()
        for uid in (
            "security-monitoring-mysql", "luck-security-events",
            "luck-security-consumers", "luck-security-lag-high",
            "luck-security-lag-critical", "luck-security-message-stale",
            "luck-security-dlq-detected", "luck-security-sink-down",
            "luck-ids-flood-detected",
        ):
            self.assertIn(uid, runtime_test)
        self.assertIn(
            "https://discordapp.com/api/webhooks/*", self.installer
        )

    def test_dashboard_defaults_limit_log_queries_and_refreshes(self):
        self.assertEqual(self.consumers["time"]["from"], "now-1h")
        self.assertEqual(self.consumers["refresh"], "5s")
        masked_panel = next(
            panel for panel in self.consumers["panels"]
            if panel["title"] == "마스킹된 챗봇 요청 · 응답 로그"
        )
        self.assertEqual(sum(target["maxLines"] for target in masked_panel["targets"]), 200)
        self.assertEqual(self.events["time"]["from"], "now-1h")
        self.assertEqual(self.events["refresh"], "1m")
        for dashboard in (self.events, self.consumers):
            self.assertEqual(dashboard["timepicker"]["time_options"], ["1h", "6h", "24h"])

    def test_grafana_is_loopback_auth_proxy_only(self):
        for value in (
            "http_addr = 127.0.0.1", "root_url = https://%(domain)s/grafana/",
            "serve_from_sub_path = true", "allow_embedding = true",
            "disable_login_form = true", "enabled = false", "header_name = X-WEBAUTH-USER",
            "whitelist = 127.0.0.1",
        ):
            self.assertIn(value, self.grafana_ini)
        self.assertIn("/etc/grafana/grafana.ini", self.installer)

    def test_nginx_requires_admin_and_removes_client_identity(self):
        for value in (
            "location = /dashboard", "location /grafana/", "auth_request /_auth/admin",
            "location = /_auth/admin", "internal;", "auth_request_set $grafana_user $upstream_http_x_auth_request_user",
            "proxy_set_header X-WEBAUTH-USER $grafana_user", "proxy_set_header X-WEBAUTH-ROLE \"\"",
            "proxy_set_header Authorization \"\"", "proxy_set_header Cookie \"\"",
            "proxy_pass http://127.0.0.1:3000", "Content-Security-Policy \"frame-ancestors 'self'\"",
            "X-Frame-Options \"SAMEORIGIN\"", "proxy_set_header Upgrade $http_upgrade",
        ):
            self.assertIn(value, self.nginx)
        self.assertIn("ss -ltn", self.part14_runner)
        self.assertIn("for _ in {1..20}", self.part14_runner)
        self.assertIn("GF_SERVER_(HTTP_ADDR|HTTP_PORT|ROOT_URL|SERVE_FROM_SUB_PATH)", self.part14_runner)
        self.assertIn("dashboards/security-monitoring", self.part14_runner)


if __name__ == "__main__":
    unittest.main()
