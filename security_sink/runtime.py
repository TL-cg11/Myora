"""Runtime configuration shared by security sink workers."""

from __future__ import annotations

import os
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
