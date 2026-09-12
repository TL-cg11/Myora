"""Security-event notification thresholds and deterministic queue keys."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable


RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
VALID_CHANNELS = ("DISCORD",)


@dataclass(frozen=True)
class NotificationPolicy:
    immediate_risk_level: str = "HIGH"
    repeated_behavior_matches: int = 3
    group_window_seconds: int = 60
    max_batch_size: int = 20
    max_retries: int = 5
    retry_base_seconds: int = 60
    retry_jitter_seconds: int = 5
    unresolved_hours_low: int = 72
    unresolved_hours_medium: int = 24
    unresolved_hours_high: int = 4
    unresolved_hours_critical: int = 1

    def unresolved_hours(self, risk_level: str) -> int:
        return {
            "LOW": self.unresolved_hours_low,
            "MEDIUM": self.unresolved_hours_medium,
            "HIGH": self.unresolved_hours_high,
            "CRITICAL": self.unresolved_hours_critical,
        }[risk_level]

    def retry_delay(
        self,
        retry_count: int,
        *,
        retry_after_seconds: float | None = None,
        jitter_seconds: float = 0,
    ) -> timedelta:
        exponent = max(0, retry_count - 1)
        backoff = min(3600, self.retry_base_seconds * (2**exponent))
        provider_delay = max(0, min(86_400, retry_after_seconds or 0))
        jitter = max(0, min(self.retry_jitter_seconds, jitter_seconds))
        return timedelta(seconds=max(backoff, provider_delay) + jitter)


DEFAULT_POLICY = NotificationPolicy()


def configured_channels(raw: str | None = None) -> tuple[str, ...]:
    value = raw if raw is not None else os.getenv("SECURITY_NOTIFICATION_CHANNELS", "DISCORD")
    channels = tuple(dict.fromkeys(item.strip().upper() for item in value.split(",") if item.strip()))
    if not channels or any(channel not in VALID_CHANNELS for channel in channels):
        raise ValueError("SECURITY_NOTIFICATION_CHANNELS must contain only DISCORD")
    return channels


def initial_alert_types(
    event: dict[str, Any], policy: NotificationPolicy = DEFAULT_POLICY
) -> tuple[str, ...]:
    alerts: list[str] = []
    risk_level = str(event["risk_level"])
    if RISK_ORDER[risk_level] >= RISK_ORDER[policy.immediate_risk_level]:
        alerts.append(f"RISK_{risk_level}")
    repeated = any(
        detection.get("category") == "BEHAVIOR"
        and int(detection.get("match_count", 0)) >= policy.repeated_behavior_matches
        for detection in event.get("detections", ())
    )
    if repeated:
        alerts.append("REPEATED_BEHAVIOR")
    return tuple(alerts)


def dedup_key(event_id: str, alert_type: str, channel: str) -> str:
    key = f"{event_id}:{alert_type}:{channel}"
    if len(key) > 255:
        raise ValueError("notification dedup key exceeds 255 characters")
    return key


def queue_rows(
    event: dict[str, Any],
    channels: Iterable[str],
    policy: NotificationPolicy = DEFAULT_POLICY,
) -> tuple[tuple[str, str, str, str, datetime], ...]:
    scheduled_at = datetime.utcnow() + timedelta(seconds=policy.group_window_seconds)
    return tuple(
        (
            dedup_key(event["event_id"], alert_type, channel),
            event["event_id"],
            alert_type,
            channel,
            scheduled_at,
        )
        for alert_type in initial_alert_types(event, policy)
        for channel in channels
    )
