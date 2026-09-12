-- Remove only synthetic Part 13-11 performance rows after results are captured.
USE security_monitoring;
START TRANSACTION;

SELECT COUNT(*) AS performance_events_before
FROM security_event WHERE event_id LIKE 'p13perf-%';
SELECT COUNT(*) AS performance_consumption_before
FROM kafka_consumption WHERE event_id LIKE 'p13perf-%';

DELETE FROM notification_log WHERE event_id LIKE 'p13perf-%';
DELETE d FROM security_event_detection d
JOIN security_event e ON e.id = d.security_event_id
WHERE e.event_id LIKE 'p13perf-%';
DELETE a FROM security_event_action a
JOIN security_event e ON e.id = a.security_event_id
WHERE e.event_id LIKE 'p13perf-%';
DELETE FROM kafka_consumption WHERE event_id LIKE 'p13perf-%';
DELETE FROM consumer_failure WHERE event_id LIKE 'p13perf-%';
DELETE FROM security_event WHERE event_id LIKE 'p13perf-%';

COMMIT;
SELECT COUNT(*) AS performance_events_after
FROM security_event WHERE event_id LIKE 'p13perf-%';
SELECT COUNT(*) AS performance_consumption_after
FROM kafka_consumption WHERE event_id LIKE 'p13perf-%';
