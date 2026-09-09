# 탐지 패키지 진입점: 다른 모듈이 process_log를 바로 가져올 수 있게 공개한다.
"""Kafka-independent security detector."""

from .engine import process_log

__all__ = ["process_log"]
