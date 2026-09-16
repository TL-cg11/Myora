-- Part 22: notification type summaries read only rule/category/risk metadata.
-- Existing notifier permissions remain least-privilege: no event mutation or deletion.
GRANT SELECT ON security_monitoring.security_event_detection TO security_monitoring_notifier;
