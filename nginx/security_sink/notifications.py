"""Durable, grouped Discord delivery for security notifications."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Iterable, Protocol
from urllib.error import HTTPError
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
       e.detected_at, e.masked_excerpt, e.source_type
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

SELECT_DETECTION_RULES = """
SELECT e.event_id, d.rule_id, d.category, d.risk_level
FROM security_event e
JOIN security_event_detection d ON d.security_event_id = e.id
WHERE e.event_id IN ({placeholders})
ORDER BY e.event_id ASC,
         FIELD(d.risk_level, 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'),
         d.rule_id ASC
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
    source_type: str = ""
    detection_rules: tuple[tuple[str, str, str], ...] = ()


class NotificationSender(Protocol):
    def send(self, subject: str, body: str) -> None: ...


class DiscordRateLimitError(RuntimeError):
    """Sanitized Discord 429 carrying only a bounded retry delay."""

    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__("Discord delivery was rate limited")
        self.retry_after_seconds = max(0, min(86_400, retry_after_seconds))


class NotificationRepository:
    def __init__(
        self,
        connection_factory: Callable[[], Any],
        policy: NotificationPolicy = DEFAULT_POLICY,
        channels: Iterable[str] | None = None,
        jitter_source: Callable[[], float] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self.policy = policy
        self.channels = tuple(channels or configured_channels())
        self._jitter_source = jitter_source or random.random

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
                        SELECT_DETECTION_RULES.format(placeholders=placeholders),
                        tuple(item.event_id for item in notifications),
                    )
                    rules_by_event: dict[str, list[tuple[str, str, str]]] = {}
                    for event_id, rule_id, category, risk_level in cursor.fetchall():
                        rules_by_event.setdefault(str(event_id), []).append(
                            (str(rule_id), str(category), str(risk_level))
                        )
                    notifications = [
                        PendingNotification(
                            item.id, item.event_id, item.alert_type, item.channel,
                            item.retry_count, item.risk_level, item.status,
                            item.source_service, item.event_name, item.detected_at,
                            item.masked_excerpt, item.source_type,
                            tuple(rules_by_event.get(item.event_id, ())),
                        )
                        for item in notifications
                    ]
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
                    retry_after = getattr(error, "retry_after_seconds", None)
                    jitter = self.policy.retry_jitter_seconds * max(
                        0, min(1, self._jitter_source())
                    )
                    next_retry = (
                        current
                        + self.policy.retry_delay(
                            next_count,
                            retry_after_seconds=retry_after,
                            jitter_seconds=jitter,
                        )
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

    @staticmethod
    def _retry_after_seconds(error: HTTPError) -> float:
        header = error.headers.get("Retry-After") if error.headers else None
        if header:
            try:
                return max(0, float(header))
            except ValueError:
                try:
                    target = parsedate_to_datetime(header)
                    now = datetime.now(target.tzinfo) if target.tzinfo else datetime.utcnow()
                    return max(0, (target.replace(tzinfo=target.tzinfo) - now).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        try:
            body = json.loads(error.read(4096).decode("utf-8"))
            return max(0, float(body.get("retry_after", 1)))
        except (AttributeError, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            return 1

    def send(self, subject: str, body: str) -> None:
        # Discord collapses an empty first line. A zero-width spacer keeps the
        # requested visual gap without exposing data or creating a mention.
        header = f"\u200b\n**{subject}**"
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
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    if not 200 <= response.status < 300:
                        raise RuntimeError("Discord delivery returned a non-success status")
            except HTTPError as exc:
                if exc.code == 429:
                    raise DiscordRateLimitError(
                        self._retry_after_seconds(exc)
                    ) from None
                raise


KST = timezone(timedelta(hours=9))

RISK_LABELS = {
    "LOW": ("낮음", "🟢"),
    "MEDIUM": ("주의", "🟡"),
    "HIGH": ("높음", "🟠"),
    "CRITICAL": ("긴급", "🔴"),
}

STATUS_LABELS = {
    "OPEN": "미처리",
    "INVESTIGATING": "조사 중",
    "RESOLVED": "처리 완료",
    "FALSE_POSITIVE": "오탐",
}

SERVICE_LABELS = {
    "luck-was": "WAS 애플리케이션",
    "luck-nginx": "Nginx",
}

EVENT_LABELS = {
    "saju.chat.requested": "사주 AI 상담 요청",
    "face.chat.requested": "관상 AI 상담 요청",
    "tarot.chat.requested": "타로 AI 상담 요청",
}

RULE_TYPE_LABELS = {
    "PROMPT_INJECTION": "프롬프트 인젝션 공격",
}

CATEGORY_TYPE_LABELS = {
    "PII": "개인정보 노출 시도",
    "SECRET": "비밀정보 노출 시도",
    "BEHAVIOR": "비정상 행위 탐지",
}

RISK_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _clean_display(value: str | None, *, limit: int) -> str:
    """Keep untrusted event metadata on one bounded Discord line."""

    normalized = " ".join((value or "-").split())
    return normalized[:limit] or "-"


def _alert_label(alert_type: str) -> str:
    if alert_type == "SECURITY_EVENT":
        return "신규 보안 이벤트"
    if alert_type.startswith("LONG_UNRESOLVED_"):
        parts = alert_type.rsplit("_", 2)
        if len(parts) == 3:
            risk = RISK_LABELS.get(parts[1], (parts[1], ""))[0]
            hours = parts[2].removesuffix("H")
            return f"장기 미처리 이벤트 ({risk}, {hours}시간 이상)"
    return _clean_display(alert_type, limit=80)


def _event_label(event_name: str | None) -> str:
    if not event_name:
        return "분류되지 않은 보안 이벤트"
    return EVENT_LABELS.get(event_name, _clean_display(event_name, limit=128))


def _detected_at_kst(value: datetime) -> str:
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return utc_value.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def _detection_type_summary(
    rules: Iterable[tuple[str, str, str]],
) -> str:
    """Return a Korean, non-sensitive type summary ordered by rule severity."""

    types: dict[str, int] = {}
    for rule_id, category, risk_level in rules:
        label = RULE_TYPE_LABELS.get(
            rule_id,
            CATEGORY_TYPE_LABELS.get(category, "기타 보안 위협 탐지"),
        )
        types[label] = min(
            types.get(label, len(RISK_ORDER)),
            RISK_ORDER.get(risk_level, len(RISK_ORDER)),
        )
    if not types:
        return "보안 위협 탐지"
    ordered = sorted(types, key=lambda label: (types[label], label))
    return ordered[0] if len(ordered) == 1 else f"{ordered[0]} 외 {len(ordered) - 1}종"


def _grafana_detail_url(
    base_url: str | None,
    event_id: str,
    detected_at: datetime,
) -> str | None:
    if not base_url:
        return None
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    utc_value = detected_at.replace(tzinfo=timezone.utc) if detected_at.tzinfo is None else detected_at.astimezone(timezone.utc)
    center = int(utc_value.timestamp() * 1000)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "var-event_id": _clean_display(event_id, limit=64),
            "from": str(center - 300_000),
            "to": str(center + 300_000),
        }
    )
    return urlunsplit(parsed._replace(query=urlencode(query)))


def render_batch(
    items: Iterable[PendingNotification],
    *,
    grafana_events_url: str | None = None,
) -> tuple[str, str]:
    notifications = tuple(items)
    if not notifications:
        raise ValueError("cannot render an empty notification batch")
    blocks = []
    for item in notifications:
        validate_masking_safety(item.masked_excerpt)
        risk_label, risk_icon = RISK_LABELS.get(
            item.risk_level,
            (_clean_display(item.risk_level, limit=32), "⚪"),
        )
        if item.alert_type == "SECURITY_EVENT" and item.source_type == "chat_request":
            lines = [
                f"{risk_icon} **위험도 {risk_label}**",
                f"• 탐지 유형: {_detection_type_summary(item.detection_rules)}",
                "• 처리 상태: 탐지 및 마스킹 완료",
                f"• 탐지 시각: {_detected_at_kst(item.detected_at)}",
            ]
            detail_url = _grafana_detail_url(
                grafana_events_url, item.event_id, item.detected_at
            )
            if detail_url:
                lines.append(f"• [Grafana에서 사건 상세 보기]({detail_url})")
            blocks.append("\n".join(lines))
            continue

        status_label = STATUS_LABELS.get(item.status, _clean_display(item.status, limit=32))
        service_label = SERVICE_LABELS.get(item.source_service, _clean_display(item.source_service, limit=64))
        blocks.append(
            "\n".join(
                (
                    f"{risk_icon} **위험도 {risk_label}**",
                    f"• 알림: {_alert_label(item.alert_type)}",
                    f"• 탐지 유형: {_event_label(item.event_name)}",
                    f"• 발생 서비스: {service_label}",
                    f"• 처리 상태: {status_label}",
                    f"• 탐지 시각: {_detected_at_kst(item.detected_at)}",
                )
            )
        )
    return f"Luck 보안 알림 {len(notifications)}건", "\n\n".join(blocks)


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepository,
        senders: dict[str, NotificationSender],
        grafana_events_url: str | None = None,
    ) -> None:
        self.repository = repository
        self.senders = senders
        self.grafana_events_url = grafana_events_url

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
                subject, body = render_batch(
                    safe_items, grafana_events_url=self.grafana_events_url
                )
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
