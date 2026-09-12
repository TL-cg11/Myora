-- 보안 알림 채널을 Discord 단일 채널로 전환 (luck-nginx security_sink 커밋 "보안 알림을 Discord 단일 채널로 전환" 대응).
-- 2026-09-07 마이그레이션의 notification_log.channel 은 ENUM('SLACK','EMAIL') 이라
-- sink 가 'DISCORD' 를 INSERT 하면 실패한다. 기존 SLACK/EMAIL 이력 값은 보존한다.
-- 적용: sudo mysql -uroot < sql/migrate/2026-09-10_notification_discord.sql
USE security_monitoring;

ALTER TABLE notification_log
    MODIFY channel ENUM('DISCORD','SLACK','EMAIL') NOT NULL;
