-- Part 13-10: disposable expired rows for an actual retention execution test.
-- Run on the MariaDB host with: sudo mariadb < scripts/part13-retention-fixture.sql

USE security_monitoring;
START TRANSACTION;

SET @fixture_tag = CONCAT('part13-retention-', REPLACE(UUID(), '-', ''));
SET @fixture_event_id = CONCAT(@fixture_tag, '-event');
SET @fixture_offset = UNIX_TIMESTAMP(UTC_TIMESTAMP(3)) * 1000
    + FLOOR(MICROSECOND(UTC_TIMESTAMP(3)) / 1000);

INSERT INTO security_event (
    event_id, source_event_id, schema_version, occurred_at, detected_at,
    environment, source_service, source_type, event_name, risk_level,
    risk_score, detector_version, masking_policy_version, status
) VALUES (
    @fixture_event_id, CONCAT(@fixture_tag, '-source'), '1.0',
    UTC_TIMESTAMP(3) - INTERVAL 400 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 400 DAY,
    'retention-test', 'part13-retention', 'synthetic', 'retention_fixture',
    'LOW', 1, 'test', 'test', 'RESOLVED'
);
SET @fixture_event_pk = LAST_INSERT_ID();

INSERT INTO security_event_detection (
    security_event_id, detection_id, rule_id, rule_version, category,
    entity_type, risk_level, confidence, match_count
) VALUES (
    @fixture_event_pk, CONCAT(@fixture_tag, '-detection'),
    'part13-retention', '1', 'RETENTION_TEST', 'fixture', 'LOW', 1.0000, 1
);

INSERT INTO security_event_action (
    security_event_id, action_type, actor_type, actor_id, acted_at
) VALUES (
    @fixture_event_pk, 'RESOLVED', 'SYSTEM', 'part13-retention',
    UTC_TIMESTAMP(3) - INTERVAL 400 DAY
);

INSERT INTO kafka_consumption (
    consumer_group, topic_name, partition_number, message_offset,
    message_key, event_id, processing_status, processed_at
) VALUES (
    'part13-retention-fixture', 'part13.retention', 0, @fixture_offset,
    @fixture_tag, @fixture_event_id, 'PROCESSED',
    UTC_TIMESTAMP(3) - INTERVAL 20 DAY
);

INSERT INTO consumer_failure (
    consumer_group, source_topic, partition_number, message_offset,
    event_id, failure_stage, error_code, error_message, retry_count,
    retry_status, first_failed_at, last_failed_at, recovered_at
) VALUES (
    'part13-retention-fixture', 'part13.retention', 0, @fixture_offset,
    @fixture_event_id, 'retention_test', 'TEST_ONLY', 'synthetic fixture', 1,
    'RECOVERED', UTC_TIMESTAMP(3) - INTERVAL 100 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY
);

INSERT INTO notification_log (
    dedup_key, event_id, alert_type, channel, status, retry_count,
    scheduled_at, sent_at, created_at, updated_at
) VALUES (
    CONCAT(@fixture_tag, '-notification'), @fixture_event_id,
    'RETENTION_TEST', 'DISCORD', 'SENT', 0,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY,
    UTC_TIMESTAMP(3) - INTERVAL 100 DAY
);

COMMIT;
SELECT @fixture_tag AS fixture_tag, @fixture_event_id AS event_id;
