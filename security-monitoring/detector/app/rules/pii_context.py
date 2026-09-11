"""정규식 PII 후보를 주변 문맥으로 재검증하는 선택형 한국어 NLI 모델."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from ..models import Detection


DEFAULT_MODEL = "Huffon/klue-roberta-base-nli"
VERIFIABLE_RULES = frozenset({"PHONE_NUMBER", "EMAIL_ADDRESS"})
SENSITIVE_LABEL = "실제 개인의 연락처 개인정보"
NON_PII_LABEL = "개인정보가 아닌 예시, 주문번호, 시스템 식별자 또는 업무 코드"


class PIICandidateVerifier(Protocol):
    """엔진이 구체적인 문맥 모델 구현과 분리된 채 사용하는 인터페이스."""

    def verify(self, text: str, candidates: list[Detection]) -> list[Detection]: ...


class PIIContextConfigurationError(RuntimeError):
    """문맥 분류 의존성이나 모델을 안전하게 초기화하지 못한 상태."""


class TransformersPIICandidateVerifier:
    """정규식 후보 중 명백한 비개인정보만 제외하는 보수적 zero-shot 검증기."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        non_pii_threshold: float = 0.90,
        local_files_only: bool = False,
        context_chars: int = 160,
        inference: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        if (
            not model_name
            or not 0.5 <= non_pii_threshold <= 1
            or context_chars < 40
        ):
            raise PIIContextConfigurationError("INVALID_PII_CONTEXT_CONFIG")
        self.model_name = model_name
        self.non_pii_threshold = non_pii_threshold
        self.context_chars = context_chars
        if inference is not None:
            self._inference = inference
            return
        try:
            from transformers import (AutoModelForSequenceClassification,
                                      AutoTokenizer)
            import torch

            self._tokenizer = AutoTokenizer.from_pretrained(
                model_name, local_files_only=local_files_only
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                model_name, local_files_only=local_files_only
            )
            label2id = {
                str(label).lower(): int(index)
                for label, index in self._model.config.label2id.items()
            }
            self._entailment_id = next(
                index for label, index in label2id.items()
                if label.startswith("entail")
            )
            self._torch = torch
            self._model.eval()
            self._inference = self._model_inference
        except Exception as exc:
            # 모델 경로·토큰 같은 세부 정보가 로그에 섞이지 않게 고정 코드만 노출한다.
            raise PIIContextConfigurationError("PII_CONTEXT_MODEL_LOAD_FAILED") from exc

    def _model_inference(
        self,
        context: str,
        *,
        candidate_labels: list[str],
        hypothesis_template: str,
        multi_label: bool,
    ) -> dict[str, Any]:
        """RoBERTa의 단일 token type 제약을 지키며 zero-shot 점수를 계산한다."""
        if multi_label or not candidate_labels:
            raise RuntimeError("INVALID_PII_CONTEXT_REQUEST")
        separator = self._tokenizer.sep_token or "[SEP]"
        sequences = [
            f"{context} {separator} {hypothesis_template.format(label)}"
            for label in candidate_labels
        ]
        encoded = self._tokenizer(
            sequences,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512,
        )
        with self._torch.inference_mode():
            logits = self._model(**encoded).logits[:, self._entailment_id]
            scores = self._torch.softmax(logits, dim=0).tolist()
        return {"labels": candidate_labels, "scores": scores}

    def _marked_context(self, text: str, candidate: Detection) -> str:
        left = max(0, candidate.start - self.context_chars)
        right = min(len(text), candidate.end + self.context_chars)
        # 한 로그에 여러 후보가 있으면 다른 절의 '주문번호/전화번호' 문맥이
        # 현재 후보 판정에 섞이지 않도록 가까운 절 경계에서 한 번 더 자른다.
        separators = ",;\n.!?。！？"
        local_left = max((text.rfind(mark, left, candidate.start) for mark in separators),
                         default=-1)
        if local_left >= left:
            left = local_left + 1
        local_rights = [
            position
            for mark in separators
            if (position := text.find(mark, candidate.end, right)) >= 0
        ]
        if local_rights:
            right = min(local_rights)
        return (
            text[left:candidate.start]
            + "[후보]"
            + text[candidate.start:candidate.end]
            + "[/후보]"
            + text[candidate.end:right]
        )

    def _non_pii_score(self, context: str) -> float:
        result = self._inference(
            context,
            candidate_labels=[SENSITIVE_LABEL, NON_PII_LABEL],
            hypothesis_template="이 문장에서 [후보]로 표시한 값은 {}이다.",
            multi_label=False,
        )
        if not isinstance(result, dict):
            raise RuntimeError("INVALID_PII_CONTEXT_RESULT")
        labels = result.get("labels")
        scores = result.get("scores")
        if not isinstance(labels, list) or not isinstance(scores, list):
            raise RuntimeError("INVALID_PII_CONTEXT_RESULT")
        if len(labels) != len(scores) or NON_PII_LABEL not in labels:
            raise RuntimeError("INVALID_PII_CONTEXT_RESULT")
        try:
            score = float(scores[labels.index(NON_PII_LABEL)])
        except (TypeError, ValueError, OverflowError) as exc:
            raise RuntimeError("INVALID_PII_CONTEXT_RESULT") from exc
        if not 0 <= score <= 1:
            raise RuntimeError("INVALID_PII_CONTEXT_RESULT")
        return score

    def verify(self, text: str, candidates: list[Detection]) -> list[Detection]:
        """고위험/비대상 규칙은 유지하고, 매우 확실한 오탐 후보만 제거한다."""
        kept: list[Detection] = []
        for candidate in candidates:
            if candidate.rule_id not in VERIFIABLE_RULES:
                kept.append(candidate)
                continue
            context = self._marked_context(text, candidate)
            if self._non_pii_score(context) < self.non_pii_threshold:
                kept.append(candidate)
        return kept
