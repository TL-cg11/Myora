"""Transformer 기반 한국어 개체명 인식 결과를 마스킹 탐지 구간으로 변환한다."""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any, Protocol

from ..models import Detection


DEFAULT_MODEL = "Leo97/KoELECTRA-small-v3-modu-ner"

# 모두의 말뭉치 대분류(PS/LC)와 일반적인 Hugging Face 라벨을 함께 받는다.
ENTITY_RULES = {
    "PS": ("PERSON_NAME", "[REDACTED_PERSON]", 50),
    "PER": ("PERSON_NAME", "[REDACTED_PERSON]", 50),
    "PERSON": ("PERSON_NAME", "[REDACTED_PERSON]", 50),
    "LC": ("LOCATION", "[REDACTED_LOCATION]", 40),
    "LOC": ("LOCATION", "[REDACTED_LOCATION]", 40),
    "LOCATION": ("LOCATION", "[REDACTED_LOCATION]", 40),
}


class NERRecognizer(Protocol):
    """엔진이 모델 구현과 분리된 채 사용할 최소 인터페이스."""

    def detect(self, text: str) -> list[Detection]: ...


class NERConfigurationError(RuntimeError):
    """NER 의존성이나 모델을 안전하게 초기화하지 못한 상태."""


def _label(entity: dict[str, Any]) -> str:
    raw = str(entity.get("entity_group") or entity.get("entity") or "").upper()
    return raw.removeprefix("B-").removeprefix("I-")


def _level(score: int) -> str:
    return "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"


class TransformersNERRecognizer:
    """Hugging Face token-classification 모델을 한 번 로드해 재사용한다."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        threshold: float = 0.85,
        local_files_only: bool = False,
        inference: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        if not model_name or not 0 <= threshold <= 1:
            raise NERConfigurationError("INVALID_NER_CONFIG")
        self.model_name = model_name
        self.threshold = threshold
        if inference is not None:
            self._inference = inference
            return
        try:
            from transformers import (AutoModelForTokenClassification,
                                      AutoTokenizer, pipeline)

            tokenizer = AutoTokenizer.from_pretrained(
                model_name, local_files_only=local_files_only
            )
            model = AutoModelForTokenClassification.from_pretrained(
                model_name, local_files_only=local_files_only
            )
            self._inference = pipeline(
                "token-classification",
                model=model,
                tokenizer=tokenizer,
                aggregation_strategy="simple",
                device=-1,
            )
        except Exception as exc:
            # 모델 경로·토큰 같은 세부 정보는 외부 로그에 섞지 않는다.
            raise NERConfigurationError("NER_MODEL_LOAD_FAILED") from exc

    @staticmethod
    def _chunks(text: str, size: int = 400, overlap: int = 60):
        """긴 로그를 모델 입력 한도보다 작게 겹쳐 자르고 원문 offset을 보존한다."""
        if not text:
            return
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            yield start, text[start:end]
            if end == len(text):
                break
            start = end - overlap

    def detect(self, text: str) -> list[Detection]:
        if not text or text.startswith("[REDACTED") and text.endswith("]"):
            return []
        redacted = [m.span() for m in re.finditer(r"\[REDACTED(?:_[A-Z_]+)?\]", text)]
        candidates: list[Detection] = []
        for base, chunk in self._chunks(text):
            entities = self._inference(chunk)
            if not isinstance(entities, list):
                raise RuntimeError("INVALID_NER_RESULT")
            for entity in entities:
                rule = ENTITY_RULES.get(_label(entity))
                if rule is None:
                    continue
                try:
                    confidence = float(entity["score"])
                    start = base + int(entity["start"])
                    end = base + int(entity["end"])
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    raise RuntimeError("INVALID_NER_RESULT") from exc
                if confidence < self.threshold:
                    continue
                if not (base <= start < end <= base + len(chunk)):
                    raise RuntimeError("INVALID_NER_SPAN")
                if any(left < end and start < right for left, right in redacted):
                    continue
                rule_id, replacement, risk_score = rule
                candidates.append(
                    Detection(
                        rule_id,
                        "PII",
                        _level(risk_score),
                        risk_score,
                        confidence,
                        start,
                        end,
                        replacement,
                        rule_version="ner-1.0",
                    )
                )

        # 겹쳐 자른 두 chunk에서 같은 개체가 중복 검출되면 한 건으로 합친다.
        merged: list[Detection] = []
        for item in sorted(candidates, key=lambda d: (d.rule_id, d.start, d.end)):
            if merged and item.rule_id == merged[-1].rule_id and item.start < merged[-1].end:
                previous = merged[-1]
                merged[-1] = Detection(
                    previous.rule_id,
                    previous.category,
                    previous.risk_level,
                    previous.risk_score,
                    max(previous.confidence, item.confidence),
                    min(previous.start, item.start),
                    max(previous.end, item.end),
                    previous.replacement,
                    rule_version=previous.rule_version,
                )
            else:
                merged.append(item)
        return sorted(merged, key=lambda d: (d.start, d.end, d.rule_id))
