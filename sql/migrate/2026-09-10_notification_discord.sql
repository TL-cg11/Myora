-- Add Discord without removing legacy Slack/email values from audit history.
-- Apply: sudo mysql -uroot < sql/migrate/2026-09-10_notification_discord.sql

USE security_monitoring;

ALTER TABLE notification_log
    MODIFY channel ENUM('DISCORD','SLACK','EMAIL') NOT NULL;
