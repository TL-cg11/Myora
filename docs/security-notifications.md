# Security notification worker

## Thresholds and ownership

Application notifications are created for HIGH and CRITICAL events, behavior
detections whose `match_count` is at least 3, and unresolved events. Unresolved
thresholds are CRITICAL 1 hour, HIGH 4 hours, MEDIUM 24 hours, and LOW 72 hours.
The security-event sink queues immediate alerts in the event DB transaction;
the notifier polls unresolved events once per minute.

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

The worker claims no more than 20 rows per cycle and sends one grouped message
per channel. A failed delivery becomes `FAILED`, increments `retry_count`, and
uses 1, 2, 4, 8 minute exponential backoff for at most 5 attempts. Success is
`SENT`; disabled channels and unsafe message content become `SUPPRESSED`.
Provider exception text is not persisted, and notifications contain only event
identifiers, safe classification fields, and `masked_excerpt` after a second
sensitive-data check.

## Slack and email

Slack uses an HTTPS incoming webhook. Email uses SMTP with implicit TLS when
`SMTP_USE_SSL=true`; otherwise it requires STARTTLS. Secrets are loaded from
`/etc/luck-security-notifier.env`, mode `0600`, and are never committed. Copy
`security_notifier.env.example` outside the repository, fill in the real values,
and enable only configured channels in `SECURITY_NOTIFICATION_CHANNELS`.

Grafana uses its own provisioned `Luck Security Operations` contact point with
Slack and email receivers. Its notification policy is appropriate because this
is a dedicated project Grafana instance; deploying it to a shared Grafana would
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
migration has been reapplied with the notifier INSERT grant:

```bash
sudo install -o root -g root -m 0600 security_notifier.env /etc/luck-security-notifier.env
sudo bash scripts/security-notifier-install.sh
sudo systemctl status security-notifier --no-pager
```

Successful delivery leaves `notification_log.status='SENT'`. Test rows that
must not be delivered should end as `SUPPRESSED`; transient provider failures
remain `FAILED` with a future `next_retry_at` until the fifth attempt.
