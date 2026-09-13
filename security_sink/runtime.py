"""Runtime configuration shared by security sink workers."""

from __future__ import annotations

import os
import time
from typing import Any


def required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"required environment variable is missing: {name}")
    return value


def mysql_connection() -> Any:
    import pymysql

    return pymysql.connect(
        host=required("SECURITY_DB_HOST"),
        port=int(os.getenv("SECURITY_DB_PORT", "3306")),
        user=required("SECURITY_DB_USER"),
        password=required("SECURITY_DB_PASSWORD"),
        database=os.getenv("SECURITY_DB_NAME", "security_monitoring"),
        charset="utf8mb4",
        autocommit=False,
    )


class _ReusableConnection:
    """Repository-facing connection whose close returns it to the worker."""

    def __init__(self, owner: "ReusableMySQLConnectionFactory", connection: Any) -> None:
        self._owner = owner
        self._connection = connection

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def begin(self) -> None:
        try:
            self._connection.begin()
        except Exception:
            self._owner.invalidate(self._connection)
            raise

    def commit(self) -> None:
        try:
            self._connection.commit()
        except Exception:
            self._owner.invalidate(self._connection)
            raise

    def rollback(self) -> None:
        try:
            self._connection.rollback()
        except Exception:
            self._owner.invalidate(self._connection)
            raise

    def close(self) -> None:
        """Keep the physical connection open until the worker shuts down."""


class ReusableMySQLConnectionFactory:
    """Reuse one connection in a single-threaded sink worker, reconnecting safely."""

    def __init__(
        self,
        connect: Any = mysql_connection,
        *,
        ping_interval: float = 1.0,
        clock: Any = time.monotonic,
    ) -> None:
        if ping_interval < 0:
            raise ValueError("ping_interval must not be negative")
        self._connect = connect
        self._ping_interval = ping_interval
        self._clock = clock
        self._connection: Any | None = None
        self._last_check = 0.0

    def _open(self) -> Any:
        connection = self._connect()
        set_autocommit = getattr(connection, "autocommit", None)
        if set_autocommit is not None:
            set_autocommit(True)
        return connection

    def __call__(self) -> _ReusableConnection:
        now = self._clock()
        if self._connection is None:
            self._connection = self._open()
            self._last_check = now
        elif now - self._last_check >= self._ping_interval:
            try:
                self._connection.ping(reconnect=True)
            except Exception:
                self.invalidate(self._connection)
                self._connection = self._open()
            self._last_check = now
        return _ReusableConnection(self, self._connection)

    def invalidate(self, connection: Any) -> None:
        if self._connection is connection:
            try:
                connection.close()
            except Exception:
                pass
            self._connection = None

    def close(self) -> None:
        if self._connection is not None:
            connection, self._connection = self._connection, None
            connection.close()


def kafka_config(default_group: str, group_env: str) -> dict[str, Any]:
    config: dict[str, Any] = {
        "bootstrap.servers": required("KAFKA_BOOTSTRAP_SERVERS"),
        "group.id": os.getenv(group_env, default_group),
        "auto.offset.reset": os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest"),
        "enable.auto.commit": False,
    }
    optional = {
        "security.protocol": "KAFKA_SECURITY_PROTOCOL",
        "sasl.mechanism": "KAFKA_SASL_MECHANISM",
        "sasl.username": "KAFKA_SASL_USERNAME",
        "sasl.password": "KAFKA_SASL_PASSWORD",
        "ssl.ca.location": "KAFKA_SSL_CA_LOCATION",
    }
    for key, env_name in optional.items():
        value = os.getenv(env_name)
        if value:
            config[key] = value
    return config


def kafka_producer_config(consumer_config: dict[str, Any]) -> dict[str, Any]:
    consumer_only = {
        "group.id",
        "auto.offset.reset",
        "enable.auto.commit",
    }
    return {
        key: value
        for key, value in consumer_config.items()
        if key not in consumer_only
    }
