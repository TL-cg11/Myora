# Kafka 마스킹 어댑터 진입점: 파이프라인과 설정만 공개한다.
"""Kafka adapter that masks raw WAS/Nginx logs with the offline detector engine."""

from adapter.config import Settings, load_settings
from adapter.pipeline import MaskingPipeline, OutboundMessage, PipelineResult
from adapter.policy import MaskingPolicy, load_policy

__all__ = [
    "MaskingPipeline",
    "MaskingPolicy",
    "OutboundMessage",
    "PipelineResult",
    "Settings",
    "load_policy",
    "load_settings",
]
