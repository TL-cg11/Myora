#!/usr/bin/env python3
"""Run the durable security notification queue worker."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import time
from typing import Any

from security_sink.notification_policy import NotificationPolicy, configured_channels
from security_sink.notifications import DiscordWebhookSender, NotificationRepository, NotificationService
from security_sink.runtime import mysql_connection, required


LOGGER = logging.getLogger("security-notifier")


def _integer(name: str, default: int, minimum: int = 1) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def policy_from_environment() -> NotificationPolicy:
    return NotificationPolicy(
        group_window_seconds=_integer("NOTIFICATION_GROUP_WINDOW_SECONDS", 0, 0),
        max_batch_size=_integer("NOTIFICATION_MAX_BATCH_SIZE", 20),
        max_retries=_integer("NOTIFICATION_MAX_RETRIES", 5),
        retry_base_seconds=_integer("NOTIFICATION_RETRY_BASE_SECONDS", 60),
        retry_jitter_seconds=_integer("NOTIFICATION_RETRY_JITTER_SECONDS", 5, 0),
        unresolved_hours_low=_integer("NOTIFICATION_UNRESOLVED_LOW_HOURS", 72),
        unresolved_hours_medium=_integer("NOTIFICATION_UNRESOLVED_MEDIUM_HOURS", 24),
        unresolved_hours_high=_integer("NOTIFICATION_UNRESOLVED_HIGH_HOURS", 4),
        unresolved_hours_critical=_integer("NOTIFICATION_UNRESOLVED_CRITICAL_HOURS", 1),
    )


def senders_from_environment(channels: tuple[str, ...]) -> dict[str, Any]:
    senders: dict[str, Any] = {}
    timeout = float(os.getenv("NOTIFICATION_DELIVERY_TIMEOUT_SECONDS", "10"))
    if "DISCORD" in channels:
        senders["DISCORD"] = DiscordWebhookSender(
            required("DISCORD_WEBHOOK_URL"), timeout_seconds=timeout
        )
    return senders


def run_once() -> dict[str, int]:
    channels = configured_channels()
    policy = policy_from_environment()
    repository = NotificationRepository(mysql_connection, policy, channels)
    service = NotificationService(
        repository,
        senders_from_environment(channels),
        grafana_events_url=os.getenv("GRAFANA_SECURITY_EVENTS_URL"),
    )
    return service.run_once()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process one polling cycle and exit.")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    interval = _integer("NOTIFICATION_POLL_SECONDS", 1)
    while not stopping:
        try:
            LOGGER.info("notification cycle result=%s", run_once())
        except Exception as exc:
            LOGGER.exception("notification cycle failed error=%s", type(exc).__name__)
            if args.once:
                return 1
        if args.once:
            return 0
        deadline = time.monotonic() + interval
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(1.0, deadline - time.monotonic()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
