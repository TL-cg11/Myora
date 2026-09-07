-- Security monitoring schema v1.
-- Credentials are intentionally excluded; use the companion apply script.
CREATE DATABASE IF NOT EXISTS security_monitoring
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE security_monitoring;

CREATE TABLE IF NOT EXISTS security_event (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_id VARCHAR(64) NOT NULL,
    source_event_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) NULL,
    schema_version VARCHAR(16) NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    detected_at DATETIME(3) NOT NULL,
    environment VARCHAR(32) NOT NULL,
    source_service VARCHAR(64) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    event_name VARCHAR(128) NULL,
    risk_level ENUM('LOW','MEDIUM','HIGH','CRITICAL') NOT NULL,
    risk_score TINYINT UNSIGNED NOT NULL,
    detector_version VARCHAR(32) NOT NULL,
    masking_policy_version VARCHAR(32) NOT NULL,
    masked_excerpt VARCHAR(1000) NULL,
    body_hash VARCHAR(80) NULL,
    status ENUM('OPEN','INVESTIGATING','RESOLVED','FALSE_POSITIVE') NOT NULL DEFAULT 'OPEN',
    assigned_to VARCHAR(128) NULL,
    resolution_reason TEXT NULL,
    resolved_at DATETIME(3) NULL,
    safe_metadata JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_security_event_event_id (event_id),
    KEY ix_security_event_source_event_id (source_event_id),
    KEY ix_security_event_request_id (request_id),
    KEY ix_security_event_occurred_at (occurred_at),
    KEY ix_security_event_detected_at (detected_at),
    KEY ix_security_event_source_service (source_service),
    KEY ix_security_event_risk_level (risk_level),
    KEY ix_security_event_assigned_to (assigned_to),
    CONSTRAINT ck_security_event_risk_score CHECK (risk_score BETWEEN 0 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_event_detection (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    security_event_id BIGINT UNSIGNED NOT NULL,
    detection_id VARCHAR(64) NOT NULL,
    rule_id VARCHAR(64) NOT NULL,
    rule_version VARCHAR(32) NOT NULL,
    category VARCHAR(32) NOT NULL,
    entity_type VARCHAR(64) NOT NULL,
    risk_level ENUM('LOW','MEDIUM','HIGH','CRITICAL') NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    match_count SMALLINT UNSIGNED NOT NULL DEFAULT 1,
    evidence_fingerprint VARCHAR(80) NULL,
    locations_json JSON NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_security_event_detection_detection_id (detection_id),
    KEY ix_security_event_detection_event_id (security_event_id),
    KEY ix_security_event_detection_rule_id (rule_id),
    KEY ix_security_event_detection_category (category),
    KEY ix_security_event_detection_entity_type (entity_type),
    KEY ix_security_event_detection_created_at (created_at),
    CONSTRAINT ck_security_event_detection_confidence CHECK (confidence BETWEEN 0 AND 1),
    CONSTRAINT fk_security_event_detection_event FOREIGN KEY (security_event_id)
        REFERENCES security_event (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_event_action (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    security_event_id BIGINT UNSIGNED NOT NULL,
    action_type ENUM('CREATED','ASSIGNED','STATUS_CHANGED','COMMENTED','RESOLVED',
                     'MARKED_FALSE_POSITIVE','REOPENED') NOT NULL,
    actor_type ENUM('SYSTEM','USER') NOT NULL,
    actor_id VARCHAR(128) NOT NULL,
    previous_status VARCHAR(32) NULL,
    new_status VARCHAR(32) NULL,
    previous_assignee VARCHAR(128) NULL,
    new_assignee VARCHAR(128) NULL,
    reason TEXT NULL,
    acted_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    KEY ix_security_event_action_event_id (security_event_id),
    KEY ix_security_event_action_actor_id (actor_id),
    KEY ix_security_event_action_acted_at (acted_at),
    CONSTRAINT fk_security_event_action_event FOREIGN KEY (security_event_id)
        REFERENCES security_event (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS kafka_consumption (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    consumer_group VARCHAR(128) NOT NULL,
    topic_name VARCHAR(128) NOT NULL,
    partition_number INT UNSIGNED NOT NULL,
    message_offset BIGINT UNSIGNED NOT NULL,
    message_key VARCHAR(128) NULL,
    payload_hash VARCHAR(80) NULL,
    event_id VARCHAR(64) NULL,
    processing_status ENUM('PROCESSED','FAILED','DLQ') NOT NULL,
    processed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_kafka_consumption_message
        (consumer_group, topic_name, partition_number, message_offset),
    KEY ix_kafka_consumption_event_id (event_id),
    KEY ix_kafka_consumption_processed_at (processed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS consumer_failure (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    consumer_group VARCHAR(128) NOT NULL,
    source_topic VARCHAR(128) NOT NULL,
    partition_number INT UNSIGNED NOT NULL,
    message_offset BIGINT UNSIGNED NOT NULL,
    event_id VARCHAR(64) NULL,
    payload_hash VARCHAR(80) NULL,
    failure_stage VARCHAR(64) NOT NULL,
    error_code VARCHAR(64) NULL,
    error_message VARCHAR(1000) NOT NULL,
    retry_count INT UNSIGNED NOT NULL DEFAULT 0,
    retry_status ENUM('PENDING','RETRYING','RECOVERED','DLQ','DISCARDED') NOT NULL DEFAULT 'PENDING',
    first_failed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    last_failed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    recovered_at DATETIME(3) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_consumer_failure_message
        (consumer_group, source_topic, partition_number, message_offset),
    KEY ix_consumer_failure_event_id (event_id),
    KEY ix_consumer_failure_last_failed_at (last_failed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    dedup_key VARCHAR(255) NOT NULL,
    event_id VARCHAR(64) NULL,
    alert_type VARCHAR(64) NOT NULL,
    channel ENUM('SLACK','EMAIL') NOT NULL,
    status ENUM('PENDING','SENDING','SENT','FAILED','SUPPRESSED') NOT NULL DEFAULT 'PENDING',
    retry_count INT UNSIGNED NOT NULL DEFAULT 0,
    next_retry_at DATETIME(3) NULL,
    last_error VARCHAR(1000) NULL,
    scheduled_at DATETIME(3) NOT NULL,
    sent_at DATETIME(3) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_notification_log_dedup_key (dedup_key),
    KEY ix_notification_log_event_id (event_id),
    KEY ix_notification_log_next_retry_at (next_retry_at),
    KEY ix_notification_log_scheduled_at (scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_user (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    actor_id VARCHAR(128) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    status ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_security_user_actor_id (actor_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_role (
    id SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    role_code VARCHAR(32) NOT NULL,
    description VARCHAR(255) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_security_role_role_code (role_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS security_user_role (
    user_id BIGINT UNSIGNED NOT NULL,
    role_id SMALLINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_security_user_role_user FOREIGN KEY (user_id)
        REFERENCES security_user (id) ON DELETE CASCADE,
    CONSTRAINT fk_security_user_role_role FOREIGN KEY (role_id)
        REFERENCES security_role (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO security_role (role_code, description) VALUES
    ('VIEWER', 'Read-only security event and audit-log access'),
    ('EDITOR', 'Security event triage and assignment access'),
    ('ADMIN', 'Security-monitoring user and role administration');

CREATE ROLE IF NOT EXISTS security_monitoring_migration;
CREATE ROLE IF NOT EXISTS security_monitoring_sink;
CREATE ROLE IF NOT EXISTS security_monitoring_api;
CREATE ROLE IF NOT EXISTS security_monitoring_readonly;
CREATE ROLE IF NOT EXISTS security_monitoring_notifier;
CREATE ROLE IF NOT EXISTS security_monitoring_retention;

GRANT ALL PRIVILEGES ON security_monitoring.* TO security_monitoring_migration;
GRANT SELECT, INSERT ON security_monitoring.security_event TO security_monitoring_sink;
GRANT SELECT, INSERT ON security_monitoring.security_event_detection TO security_monitoring_sink;
GRANT SELECT, INSERT ON security_monitoring.security_event_action TO security_monitoring_sink;
GRANT SELECT, INSERT ON security_monitoring.kafka_consumption TO security_monitoring_sink;
GRANT SELECT, INSERT, UPDATE ON security_monitoring.consumer_failure TO security_monitoring_sink;
GRANT SELECT, INSERT ON security_monitoring.notification_log TO security_monitoring_sink;
GRANT SELECT, UPDATE ON security_monitoring.security_event TO security_monitoring_api;
GRANT SELECT, INSERT ON security_monitoring.security_event_action TO security_monitoring_api;
GRANT SELECT, INSERT, UPDATE ON security_monitoring.security_user TO security_monitoring_api;
GRANT SELECT ON security_monitoring.security_role TO security_monitoring_api;
GRANT SELECT, INSERT, DELETE ON security_monitoring.security_user_role TO security_monitoring_api;
GRANT SELECT ON security_monitoring.security_event_detection TO security_monitoring_api;
GRANT SELECT ON security_monitoring.kafka_consumption TO security_monitoring_api;
GRANT SELECT ON security_monitoring.consumer_failure TO security_monitoring_api;
GRANT SELECT ON security_monitoring.notification_log TO security_monitoring_api;
GRANT SELECT ON security_monitoring.* TO security_monitoring_readonly;

-- The notifier changes only delivery state. It reads the event only to compose
-- a notification and cannot insert, delete, or alter security events.
GRANT SELECT, UPDATE ON security_monitoring.notification_log TO security_monitoring_notifier;
GRANT SELECT ON security_monitoring.security_event TO security_monitoring_notifier;

-- Retention deletes only documented retention data. Its worker must delete
-- detection/action children before their security_event parent in each batch.
GRANT SELECT, DELETE ON security_monitoring.security_event_detection TO security_monitoring_retention;
GRANT SELECT, DELETE ON security_monitoring.security_event_action TO security_monitoring_retention;
GRANT SELECT, DELETE ON security_monitoring.security_event TO security_monitoring_retention;
GRANT SELECT, DELETE ON security_monitoring.kafka_consumption TO security_monitoring_retention;
GRANT SELECT, DELETE ON security_monitoring.consumer_failure TO security_monitoring_retention;
GRANT SELECT, DELETE ON security_monitoring.notification_log TO security_monitoring_retention;
