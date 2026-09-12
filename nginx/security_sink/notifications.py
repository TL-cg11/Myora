"""Durable, grouped Discord delivery for security notifications."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from security_sink.common import validate_masking_safety
from security_sink.notification_policy import (
    DEFAULT_POLICY,
    NotificationPolicy,
    configured_channels,
    dedup_key,
)


INSERT_NOTIFICATION = """
INSERT IGNORE INTO notification_log (
    dedup_key, event_id, alert_type, channel, status, scheduled_at
) VALUES (%s, %s, %s, %s, 'PENDING', %s)
""".strip()

SELECT_UNRESOLVED = """
SELECT event_id, risk_level, detected_at
FROM security_event
WHERE status IN ('OPEN', 'INVESTIGATING')
  AND detected_at <= UTC_TIMESTAMP(3) - INTERVAL 1 HOUR
ORDER BY detected_at ASC
LIMIT %s
""".strip()

SELECT_DUE = """
SELECT n.id, n.event_id, n.alert_type, n.channel, n.retry_count,
       e.risk_level, e.status, e.source_service, e.event_name,
       e.detected_at, e.masked_excerpt
FROM notification_log n
JOIN security_event e ON e.event_id = n.event_id
WHERE (
        n.status IN ('PENDING', 'FAILED')
        OR (n.status = 'SENDING' AND n.updated_at < UTC_TIMESTAMP(3) - INTERVAL 10 MINUTE)
      )
  AND n.retry_count < %s
  AND n.scheduled_at <= UTC_TIMESTAMP(3)
  AND (n.next_retry_at IS NULL OR n.next_retry_at <= UTC_TIMESTAMP(3))
ORDER BY n.scheduled_at ASC, n.id ASC
LIMIT %s
FOR UPDATE SKIP LOCKED
""".strip()


@dataclass(frozen=True)
class PendingNotification:
    id: int
    event_id: str
    alert_type: str
    channel: str
    retry_count: int
    risk_level: str
    status: str
    source_service: str
    event_name: str | None
    detected_at: datetime
    masked_excerpt: str | None


class NotificationSender(Protocol):
    def send(self, subject: str, body: str) -> None: ...


class NotificationRepository:
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        policy: NotificationPolicy = DEFAULT_POLICY,
        channels: Iterable[str] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self.policy = policy
        self.channels = tuple(channels or configured_channels())

    def schedule_unresolved(self, now: datetime | None = None, limit: int = 500) -> int:
        current = now or datetime.utcnow()
        connection = self._connection_factory()
        inserted = 0
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(SELECT_UNRESOLVED, (limit,))
                for event_id, risk_level, detected_at in cursor.fetchall():
                    hours = self.policy.unresolved_hours(str(risk_level))
                    if detected_at > current - timedelta(hours=hours):
                        continue
                    alert_type = f"LONG_UNRESOLVED_{risk_level}_{hours}H"
                    for channel in self.channels:
                        cursor.execute(
                            INSERT_NOTIFICATION,
                            (
                                dedup_key(str(event_id), alert_type, channel),
                                event_id,
                                alert_type,
                                channel,
                                current,
                            ),
                        )
                        inserted += max(0, int(cursor.rowcount))
            connection.commit()
            return inserted
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def claim_due(self) -> list[PendingNotification]:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    SELECT_DUE,
                    (self.policy.max_retries, self.policy.max_batch_size),
                )
                rows = cursor.fetchall()
                notifications = [PendingNotification(*row) for row in rows]
                if notifications:
                    placeholders = ",".join(["%s"] * len(notifications))
                    cursor.execute(
                        f"UPDATE notification_log SET status = 'SENDING', updated_at = UTC_TIMESTAMP(3) WHERE id IN ({placeholders})",
                        tuple(item.id for item in notifications),
                    )
            connection.commit()
            return notifications
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_sent(self, ids: Iterable[int], sent_at: datetime | None = None) -> None:
        values = tuple(ids)
        if not values:
            return
        self._update_many(
            values,
            "status = 'SENT', sent_at = %s, next_retry_at = NULL, last_error = NULL",
            (sent_at or datetime.utcnow(),),
        )

    def mark_suppressed(self, ids: Iterable[int], reason: str) -> None:
        values = tuple(ids)
        if values:
            self._update_many(
                values,
                "status = 'SUPPRESSED', next_retry_at = NULL, last_error = %s",
                (reason[:1000],),
            )

    def mark_failed(self, items: Iterable[PendingNotification], error: BaseException) -> None:
        safe_error = f"{type(error).__name__}: delivery failed"
        current = datetime.utcnow()
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                for item in items:
                    next_count = item.retry_count + 1
                    next_retry = (
                        current + self.policy.retry_delay(next_count)
                        if next_count < self.policy.max_retries
                        else None
                    )
                    cursor.execute(
                        """
                        UPDATE notification_log
                        SET status = 'FAILED', retry_count = %s,
                            next_retry_at = %s, last_error = %s
                        WHERE id = %s
                        """.strip(),
                        (next_count, next_retry, safe_error, item.id),
                    )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _update_many(self, ids: tuple[int, ...], assignment: str, prefix: tuple[Any, ...]) -> None:
        placeholders = ",".join(["%s"] * len(ids))
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE notification_log SET {assignment} WHERE id IN ({placeholders})",
                    prefix + ids,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class DiscordWebhookSender:
    def __init__(self, webhook_url: str, timeout_seconds: float = 10.0) -> None:
        parsed = urlsplit(webhook_url)
        allowed_hosts = {
            "discord.com",
            "www.discord.com",
            "canary.discord.com",
            "ptb.discord.com",
            "discordapp.com",
            "www.discordapp.com",
        }
        if (
            parsed.scheme != "https"
            or parsed.hostname not in allowed_hosts
            or not parsed.path.startswith("/api/webhooks/")
        ):
            raise ValueError("Discord webhook URL must use the official HTTPS endpoint")
        if parsed.hostname in {"discordapp.com", "www.discordapp.com"}:
            parsed = parsed._replace(netloc="discord.com")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["wait"] = "true"
        self.webhook_url = urlunsplit(parsed._replace(query=urlencode(query)))
        self.timeout_seconds = timeout_seconds

    def send(self, subject: str, body: str) -> None:
        header = f"**{subject}**"
        chunks: list[str] = []
        current = header
        for line in body.splitlines():
            candidate = f"{current}\n{line}"
            if len(candidate) <= 2000:
                current = candidate
                continue
            chunks.append(current)
            current = f"{header}\n{line}"
        chunks.append(current)

        for content in chunks:
            payload = json.dumps(
                {"content": content, "allowed_mentions": {"parse": []}}
            ).encode("utf-8")
            request = Request(
                self.webhook_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": (
                        "DiscordBot (https://github.com/TL-cg11/luck-nginx, 1.0)"
                    ),
                },
                method="POST",
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError("Discord delivery returned a non-success status")


def render_batch(items: Iterable[PendingNotification]) -> tuple[str, str]:
    notifications = tuple(items)
    if not notifications:
        raise ValueError("cannot render an empty notification batch")
    lines = []
    for item in notifications:
        validate_masking_safety(item.masked_excerpt)
        excerpt = (item.masked_excerpt or "-").replace("\n", " ")[:240]
        lines.append(
            f"[{item.risk_level}] event_id={item.event_id} alert={item.alert_type} "
            f"service={item.source_service} status={item.status} "
            f"detected_at={item.detected_at.isoformat()}Z excerpt={excerpt}"
        )
    return f"Luck security alerts ({len(notifications)})", "\n".join(lines)


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        senders: dict[str, NotificationSender],
    ) -> None:
        self.repository = repository
        self.senders = senders

    def run_once(self, now: datetime | None = None) -> dict[str, int]:
        scheduled = self.repository.schedule_unresolved(now=now)
        claimed = self.repository.claim_due()
        sent = failed = suppressed = 0
        grouped: dict[str, list[PendingNotification]] = {}
        for item in claimed:
            grouped.setdefault(item.channel, []).append(item)
        for channel, items in grouped.items():
            sender = self.senders.get(channel)
            if sender is None:
                self.repository.mark_suppressed(
                    (item.id for item in items), "channel is not configured"
                )
                suppressed += len(items)
                continue
            safe_items: list[PendingNotification] = []
            for item in items:
                try:
                    validate_masking_safety(item.masked_excerpt)
                    safe_items.append(item)
                except ValueError:
                    self.repository.mark_suppressed((item.id,), "unsafe notification payload")
                    suppressed += 1
            if not safe_items:
                continue
            try:
                subject, body = render_batch(safe_items)
                sender.send(subject, body)
                self.repository.mark_sent(item.id for item in safe_items)
                sent += len(safe_items)
            except Exception as exc:
                self.repository.mark_failed(safe_items, exc)
                failed += len(safe_items)
        return {
            "scheduled": scheduled,
            "claimed": len(claimed),
            "sent": sent,
            "failed": failed,
            "suppressed": suppressed,
        }
