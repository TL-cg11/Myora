# Security notification worker

## Thresholds and ownership

Application notifications are created only when a newly persisted, detector-
masked `source_type=chat_request` security event is received. `chat_response`,
general API, and AI-internal logs do not create a direct Discord notification.
Each eligible event uses the `SECURITY_EVENT` alert type and the deterministic
`event_id:alert_type:channel` key. Unresolved thresholds remain CRITICAL 1 hour,
HIGH 4 hours, MEDIUM 24 hours, and LOW 72 hours.

Grafana owns metric-based infrastructure alerts. The notifier owns only the
masked chatbot-request detection notice, so DLQ, consumer lag/stale, target-down
and IDS Flood incidents cannot be sent twice by this worker.

Grafana owns metric-based infrastructure alerts. Lag warning is 1,000 messages
for 5 minutes; critical is 5,000 messages immediately or oldest-message age over
60 seconds. Any DLQ increase in 5 minutes and a scrape target down for 2 minutes
are critical. Grafana groups notifications for 30 seconds, waits 5 minutes for
new alerts in an existing group, and repeats an unchanged firing alert after 4
hours.

## Idempotency, grouping, and retries

Each application queue row has a deterministic
`event_id:alert_type:channel` key backed by the existing UNIQUE constraint.
`INSERT IGNORE` makes event redelivery and unresolved polling idempotent. Due
rows are claimed with `FOR UPDATE SKIP LOCKED`, so multiple workers do not send
the same row concurrently; stale `SENDING` rows become eligible again after 10
minutes.

Each event is eligible for delivery immediately; the worker polls every second
for the demonstration target and may group rows claimed in the same cycle into one message per
channel. A failed delivery becomes `FAILED`, increments `retry_count`, and
uses 1, 2, 4, 8 minute exponential backoff plus bounded jitter for at most 5
attempts. Discord HTTP 429 responses honor a numeric or HTTP-date `Retry-After`
value (or the JSON `retry_after` fallback) without scheduling earlier than the
normal backoff. Success is `SENT`; disabled channels and unsafe message content
become `SUPPRESSED`.
Provider exception text is not persisted. Chat-request notifications contain
only a Korean detection-type summary, final masking status, risk level, detected
time, and an optional Grafana event-detail link. They never contain a raw prompt,
masked excerpt, rule evidence, or request body.

## Discord

Discord uses an official HTTPS incoming webhook with `wait=true`, accepting both
the current `discord.com` host and Discord-issued legacy `discordapp.com` URLs, so the worker
confirms that Discord accepted each message before marking rows `SENT`. Mentions
are disabled and messages longer than Discord's 2,000-character content limit
are split. The webhook is loaded from `/etc/luck-security-notifier.env`, mode
`0600`, and is never committed. `SECURITY_NOTIFICATION_CHANNELS` accepts only
`DISCORD`; Slack and email are disabled. Set `GRAFANA_SECURITY_EVENTS_URL` to
the HTTPS `luck-security-events` dashboard URL to include a link constrained to
the event ID and a five-minute detection window.

Grafana uses its own provisioned `Luck Security Operations` contact point with
a Discord receiver. Its notification policy is appropriate because this is a
dedicated project Grafana instance; deploying it to a shared Grafana would
replace that organization policy tree and must be reviewed first.

## Local and server verification

Run one worker cycle after supplying a notifier environment:

```bash
set -a
. ./security_notifier.env
set +a
.venv-security-sink/bin/python -m security_sink.notifier_worker --once
```

For the Ubuntu server, install the environment and service after the MariaDB
migration has been reapplied with the notifier detection-read grant. The
repository migration wrapper includes this follow-up grant; if only the Nginx
repository is deployed, the MariaDB owner must apply
`2026-09-16_notifier_detection_read.sql` before restarting the notifier:

```bash
sudo install -o root -g root -m 0600 security_notifier.env /etc/luck-security-notifier.env
sudo bash scripts/security-notifier-install.sh
sudo systemctl status security-notifier --no-pager
```

Successful delivery leaves `notification_log.status='SENT'`. Test rows that
must not be delivered should end as `SUPPRESSED`; transient provider failures
remain `FAILED` with a future `next_retry_at` until the fifth attempt.
