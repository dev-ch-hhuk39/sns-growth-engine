"""Fail-closed semantic alignment for source-grounded public captions."""
from __future__ import annotations

import math
import os
import re
from difflib import SequenceMatcher
from typing import Any

from acquisition.contracts import ProviderResult

ALIGNMENT_THRESHOLDS = {
    "final_alignment_score": 0.72,
    "main_claim_coverage": 0.70,
    "unsupported_claim_count": 0,
    "source_copy_similarity": 0.65,
    "recent_post_similarity": 0.75,
}


def _compact(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def _ngrams(text: str, size: int = 2) -> set[str]:
    compact = _compact(text)
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[index:index + size] for index in range(len(compact) - size + 1)}


def lexical_similarity(left: str, right: str) -> float:
    left_set, right_set = _ngrams(left), _ngrams(right)
    if not left_set or not right_set:
        return 0.0
    dice = 2 * len(left_set & right_set) / (len(left_set) + len(right_set))
    sequence = SequenceMatcher(None, _compact(left), _compact(right)).ratio()
    return round(max(dice, sequence), 4)


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。！？!?\n]+", str(text or "")) if item.strip()]


def _best_sentence_similarity(fragment: str, text: str) -> float:
    return max((lexical_similarity(fragment, sentence) for sentence in _sentences(text)), default=0.0)


def source_copy_similarity(source_text: str, public_text: str) -> float:
    source = _compact(source_text)
    public = _compact(public_text)
    if not source or not public:
        return 0.0
    sequence = SequenceMatcher(None, source, public).ratio()
    public_grams = _ngrams(public, 3)
    source_grams = _ngrams(source, 3)
    containment = len(public_grams & source_grams) / max(1, len(public_grams))
    return round(max(sequence, containment), 4)


class JapaneseEmbeddingSimilarityProvider:
    """Optional multilingual embedding scorer with a strict work cap.

    The heavyweight model is imported lazily and is never required by the
    standard runner.  A capped input count/length prevents unbounded inference.
    """

    provider_name = "sentence_transformers_multilingual"
    provider_version = "paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self, *, max_texts: int = 16, max_chars: int = 2000):
        self.max_texts = max_texts
        self.max_chars = max_chars
        self._model: Any = None

    def score(self, pairs: list[tuple[str, str]]) -> ProviderResult[list[float]]:
        if not os.environ.get("ENABLE_SENTENCE_TRANSFORMERS", "").lower() in {"1", "true", "yes"}:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="embedding_provider_disabled")
        if len(pairs) > self.max_texts or any(len(a) + len(b) > self.max_chars for a, b in pairs):
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="embedding_hard_cap_exceeded")
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
        except ImportError:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="sentence_transformers_not_installed")
        if self._model is None:
            self._model = SentenceTransformer(self.provider_version)
        flattened = [text for pair in pairs for text in pair]
        vectors = self._model.encode(flattened, normalize_embeddings=True)
        scores = [float(np.dot(vectors[index], vectors[index + 1])) for index in range(0, len(vectors), 2)]
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data=scores)


class LocalSemanticAlignmentProvider:
    provider_name = "local_semantic_alignment"
    provider_version = "1"

    def evaluate(
        self,
        *,
        source_text: str,
        public_post_text: str,
        main_claims: list[str],
        claim_support: list[dict[str, str]],
        recent_posts: list[str],
    ) -> ProviderResult[dict[str, Any]]:
        verified_support: list[dict[str, Any]] = []
        for item in claim_support:
            caption_claim = str(item.get("caption_claim", "")).strip()
            evidence = str(item.get("source_evidence", "")).strip()
            evidence_in_source = bool(evidence) and (
                _compact(evidence) in _compact(source_text)
                or _best_sentence_similarity(evidence, source_text) >= 0.58
            )
            claim_in_caption = bool(caption_claim) and (
                _compact(caption_claim) in _compact(public_post_text)
                or _best_sentence_similarity(caption_claim, public_post_text) >= 0.28
            )
            claim_evidence_similarity = lexical_similarity(caption_claim, evidence)
            verified_support.append({
                "caption_claim": caption_claim,
                "source_evidence": evidence,
                "claim_evidence_similarity": claim_evidence_similarity,
                "verified": evidence_in_source and claim_in_caption and claim_evidence_similarity >= 0.08,
            })

        covered = 0
        for claim in main_claims:
            if any(item["verified"] and lexical_similarity(claim, item["source_evidence"]) >= 0.22 for item in verified_support):
                covered += 1
        coverage = covered / max(1, len(main_claims)) if main_claims else 0.0
        unsupported = sum(1 for item in verified_support if not item["verified"])
        if not verified_support:
            unsupported = 1

        copy_score = source_copy_similarity(source_text, public_post_text)
        recent_score = max((lexical_similarity(public_post_text, row) for row in recent_posts if row), default=0.0)
        support_ratio = sum(1 for item in verified_support if item["verified"]) / max(1, len(verified_support))
        final_score = (
            0.50 * coverage
            + 0.25 * support_ratio
            + 0.15 * max(0.0, 1.0 - copy_score)
            + 0.10 * max(0.0, 1.0 - recent_score)
        )
        final_score = round(min(1.0, max(0.0, final_score)), 4)
        metrics = {
            "final_alignment_score": final_score,
            "main_claim_coverage": round(coverage, 4),
            "unsupported_claim_count": unsupported,
            "source_copy_similarity": copy_score,
            "recent_post_similarity": round(recent_score, 4),
            "verified_claim_support": verified_support,
        }
        blocked = []
        if final_score < ALIGNMENT_THRESHOLDS["final_alignment_score"]:
            blocked.append("final_alignment_score_below_threshold")
        if coverage < ALIGNMENT_THRESHOLDS["main_claim_coverage"]:
            blocked.append("main_claim_coverage_below_threshold")
        if unsupported != 0:
            blocked.append("unsupported_claims_present")
        if copy_score > ALIGNMENT_THRESHOLDS["source_copy_similarity"]:
            blocked.append("source_copy_similarity_above_threshold")
        if recent_score > ALIGNMENT_THRESHOLDS["recent_post_similarity"]:
            blocked.append("recent_post_similarity_above_threshold")
        metrics["status"] = "PASS" if not blocked else "BLOCKED"
        metrics["blocked_reasons"] = blocked
        return ProviderResult(self.provider_name, self.provider_version, "PASS" if not blocked else "BLOCKED", data=metrics, reason=",".join(blocked))
