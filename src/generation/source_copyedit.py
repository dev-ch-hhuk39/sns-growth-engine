"""Source-preserving copyedit contracts for approved direct media."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.semantic_alignment import (
    lexical_similarity,
    source_copy_similarity,
)

ROOT = Path(__file__).resolve().parents[2]
RULES_FILE = ROOT / "config" / "post_generation_rules.json"

SOURCE_PRESERVATION_MIN = 0.55
RECENT_POST_SIMILARITY_MAX = 0.75

DEFAULT_FORBIDDEN_TEMPLATE_PHRASES = (
    "確認することは一つ。",
    "この順番で考える理由はシンプル。",
    "見るポイントは次の通り。",
    "次に試すこと：",
)

DEFAULT_MARKERS = {
    "night_scout": (
        "なんだよね",
        "なんよね",
        "だよ",
        "かな",
        "と思う",
        "僕なら",
    ),
    "liver_manager": (
        "なんだよね",
        "よね",
        "大丈夫",
        "してみて",
        "かも",
        "かな",
        "私なら",
        "じゃなくて",
    ),
}


def _profile(account_id: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            RULES_FILE.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return {}

    profiles = payload.get(
        "persona_profiles",
        {},
    )

    profile = profiles.get(
        account_id,
        {},
    )

    return (
        profile
        if isinstance(
            profile,
            dict,
        )
        else {}
    )


def _compact(text: str) -> str:
    return re.sub(
        r"[\s\W_]+",
        "",
        str(text or "").lower(),
        flags=re.UNICODE,
    )


def _sentences(text: str) -> list[str]:
    return [
        item.strip()
        for item in re.split(
            r"[。！？!?\n]+",
            str(text or ""),
        )
        if item.strip()
    ]


def clean_source_post_text(
    text: str,
    account_id: str = "",
) -> str:
    """Remove transport metadata while preserving the source's claims."""

    value = str(
        text or ""
    )

    value = re.sub(
        r"https?://\S+",
        "",
        value,
    )

    value = re.sub(
        r"(?<!\S)@\S+",
        "",
        value,
    )

    value = re.sub(
        r"(?<!\S)#[^\s#]+",
        "",
        value,
    )

    value = value.replace(
        "\u3000",
        " ",
    )

    if account_id == "night_scout":
        first_person_replacements = (
            ("私は", "僕は"),
            ("私が", "僕が"),
            ("私なら", "僕なら"),
            ("わたしは", "僕は"),
            ("わたしが", "僕が"),
            ("わたしなら", "僕なら"),
            ("俺は", "僕は"),
            ("俺が", "僕が"),
            ("俺なら", "僕なら"),
            ("おれは", "僕は"),
            ("おれが", "僕が"),
            ("おれなら", "僕なら"),
        )
        for old, new in first_person_replacements:
            value = value.replace(
                old,
                new,
            )
    elif account_id == "liver_manager":
        first_person_replacements = (
            ("僕は", "私は"),
            ("僕が", "私が"),
            ("僕なら", "私なら"),
            ("ぼくは", "私は"),
            ("ぼくが", "私が"),
            ("ぼくなら", "私なら"),
            ("俺は", "私は"),
            ("俺が", "私が"),
            ("俺なら", "私なら"),
            ("おれは", "私は"),
            ("おれが", "私が"),
            ("おれなら", "私なら"),
        )
        for old, new in first_person_replacements:
            value = value.replace(old, new)

    value = re.sub(
        r"[ \t]+",
        " ",
        value,
    )

    value = re.sub(
        r"\s*([。！？!?])\s*",
        r"\1\n",
        value,
    )

    lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip()
    ]

    normalized_lines: list[str] = []

    for line in lines:
        if not re.search(
            r"[。！？!?]$",
            line,
        ):
            line += "。"

        normalized_lines.append(
            line
        )

    return "\n\n".join(
        normalized_lines
    ).strip()


def source_text_is_usable(
    text: str,
) -> bool:
    cleaned = clean_source_post_text(
        text
    )

    compact = _compact(
        cleaned
    )

    return (
        len(compact) >= 20
        and bool(
            re.search(
                r"[ぁ-んァ-ヶ一-龠々]",
                cleaned,
            )
        )
    )


def _fact_tokens(
    text: str,
) -> list[str]:
    cleaned = clean_source_post_text(
        text
    )

    numeric = re.findall(
        r"\d+(?:[.,]\d+)*(?:円|万|%|％|人|時間|分|日|回|件)?",
        cleaned,
    )

    katakana = re.findall(
        r"[ァ-ヶー]{3,}",
        cleaned,
    )

    latin = re.findall(
        r"\b[A-Z][A-Za-z0-9_.-]{2,}\b",
        cleaned,
    )

    ignored = {
        "TikTok",
        "LIVE",
        "SNS",
    }

    return sorted(
        {
            token
            for token in (
                numeric
                + katakana
                + latin
            )
            if token not in ignored
        }
    )


def _numeric_tokens(
    text: str,
) -> set[str]:
    return set(
        re.findall(
            r"\d+(?:[.,]\d+)*(?:円|万|%|％|人|時間|分|日|回|件)?",
            str(text or ""),
        )
    )


def evaluate_source_copyedit_contract(
    *,
    source_text: str,
    public_post_text: str,
    account_id: str,
    recent_posts: list[str] | None = None,
) -> dict[str, Any]:
    source = clean_source_post_text(
        source_text,
        account_id,
    )

    public = str(
        public_post_text or ""
    ).strip()

    reasons: list[str] = []

    if not source_text_is_usable(
        source
    ):
        reasons.append(
            "source_post_text_unusable"
        )

    if not public:
        reasons.append(
            "source_copyedit_empty"
        )

    preservation = (
        source_copy_similarity(
            source,
            public,
        )
        if source
        and public
        else 0.0
    )

    if (
        preservation
        < SOURCE_PRESERVATION_MIN
    ):
        reasons.append(
            "source_preservation_similarity_below_threshold"
        )

    source_facts = _fact_tokens(
        source
    )

    public_compact = _compact(
        public
    )

    missing_facts = [
        token
        for token in source_facts
        if _compact(
            token
        )
        not in public_compact
    ]

    if missing_facts:
        reasons.append(
            "source_fact_removed"
        )

    source_numbers = _numeric_tokens(
        source
    )

    public_numbers = _numeric_tokens(
        public
    )

    added_numbers = sorted(
        public_numbers
        - source_numbers
    )

    if added_numbers:
        reasons.append(
            "unsupported_numeric_claim_added"
        )

    source_sentences = _sentences(
        source
    )

    unsupported_sentences: list[str] = []

    for sentence in _sentences(
        public
    ):
        if len(
            _compact(
                sentence
            )
        ) < 6:
            continue

        best = max(
            (
                lexical_similarity(
                    sentence,
                    evidence,
                )
                for evidence
                in source_sentences
            ),
            default=0.0,
        )

        if best < 0.14:
            unsupported_sentences.append(
                sentence
            )

    if unsupported_sentences:
        reasons.append(
            "unsupported_copyedit_sentence_added"
        )

    recent_similarity = max(
        (
            lexical_similarity(
                public,
                item,
            )
            for item in (
                recent_posts
                or []
            )
            if str(
                item or ""
            ).strip()
        ),
        default=0.0,
    )

    if (
        recent_similarity
        > RECENT_POST_SIMILARITY_MAX
    ):
        reasons.append(
            "recent_post_similarity_above_threshold"
        )

    profile = _profile(
        account_id
    )

    copyedit_profile = (
        profile.get(
            "source_copyedit",
            {},
        )
        if isinstance(
            profile.get(
                "source_copyedit",
                {},
            ),
            dict,
        )
        else {}
    )

    forbidden_phrases = tuple(
        str(item)
        for item in copyedit_profile.get(
            "forbidden_template_phrases",
            DEFAULT_FORBIDDEN_TEMPLATE_PHRASES,
        )
        if str(item)
    )

    template_hits = [
        phrase
        for phrase in forbidden_phrases
        if phrase in public
    ]

    if template_hits:
        reasons.append(
            "template_recomposition_detected"
        )

    markers = tuple(
        str(item)
        for item in copyedit_profile.get(
            "preferred_markers",
            DEFAULT_MARKERS.get(
                account_id,
                (),
            ),
        )
        if str(item)
    )

    source_marker_hits = [
        marker
        for marker in markers
        if marker in source
    ]

    public_marker_hits = [
        marker
        for marker in markers
        if marker in public
    ]

    if (
        source_marker_hits
        and not public_marker_hits
    ):
        reasons.append(
            "source_voice_marker_lost"
        )

    ending_pattern = re.compile(
        r"(?:なんだよね|なんよね|だよね|だよ|よね|よな|かな)"
        r"(?:[。！？!?]|$)"
    )

    ending_count = len(
        ending_pattern.findall(
            public
        )
    )

    maximum_endings = int(
        copyedit_profile.get(
            "maximum_conversational_endings",
            2,
        )
        or 2
    )

    if (
        ending_count
        > maximum_endings
    ):
        reasons.append(
            "account_conversational_ending_overuse"
        )

    if len(public) < 20:
        reasons.append(
            "source_copyedit_too_short"
        )

    if len(public) > 520:
        reasons.append(
            "source_copyedit_too_long"
        )

    reasons = sorted(
        set(
            reasons
        )
    )

    return {
        "status": (
            "PASS"
            if not reasons
            else "BLOCKED"
        ),
        "blocked_reasons": reasons,
        "source_text": source,
        "source_preservation_similarity": round(
            preservation,
            4,
        ),
        "recent_post_similarity": round(
            recent_similarity,
            4,
        ),
        "source_fact_tokens": source_facts,
        "missing_source_fact_tokens": (
            missing_facts
        ),
        "added_numeric_tokens": (
            added_numbers
        ),
        "unsupported_sentences": (
            unsupported_sentences
        ),
        "source_voice_markers": (
            source_marker_hits
        ),
        "public_voice_markers": (
            public_marker_hits
        ),
        "conversational_ending_count": (
            ending_count
        ),
        "template_hits": template_hits,
    }



SOURCE_PRESERVING_RELAXED_REASONS = {
    "too_short",
    "naturalness_below_threshold",
    "reader_value_below_threshold",
    "account_fit_below_threshold",
    "quality_below_threshold",
    "persona_reader_context_insufficient",
    "persona_decision_support_missing",
    "persona_concrete_action_missing",
    "persona_logic_missing",
}


def validate_source_preserving_public_post(
    text: Any,
    account_id: str,
) -> dict[str, Any]:
    """Apply ordinary safety gates without forcing a new article structure."""

    from public_post_quality import (
        final_public_post_validator,
    )

    base = dict(
        final_public_post_validator(
            text,
            account_id,
        )
    )

    public_text = str(
        base.get(
            "public_post_text",
            "",
        )
    ).strip()

    original_reasons = {
        str(reason)
        for reason in base.get(
            "blocked_reasons",
            [],
        )
        if str(reason)
    }

    reasons = {
        reason
        for reason in original_reasons
        if reason
        not in SOURCE_PRESERVING_RELAXED_REASONS
    }

    if len(public_text) < 20:
        reasons.add(
            "source_copyedit_too_short"
        )

    if len(public_text) > 520:
        reasons.add(
            "source_copyedit_too_long"
        )

    profile = _profile(
        account_id
    )

    copyedit_profile = (
        profile.get(
            "source_copyedit",
            {},
        )
        if isinstance(
            profile.get(
                "source_copyedit",
                {},
            ),
            dict,
        )
        else {}
    )

    forbidden_phrases = [
        str(item)
        for item in copyedit_profile.get(
            "forbidden_template_phrases",
            DEFAULT_FORBIDDEN_TEMPLATE_PHRASES,
        )
        if str(item)
    ]

    template_hits = [
        phrase
        for phrase in forbidden_phrases
        if phrase in public_text
    ]

    if template_hits:
        reasons.add(
            "template_recomposition_detected"
        )

    ending_count = len(
        re.findall(
            r"(?:なんだよね|なんよね|"
            r"だよね|だよ|よね|よな|かな)"
            r"(?:[。！？!?]|$)",
            public_text,
        )
    )

    maximum_endings = int(
        copyedit_profile.get(
            "maximum_conversational_endings",
            2,
        )
        or 2
    )

    if ending_count > maximum_endings:
        reasons.add(
            "account_conversational_ending_overuse"
        )

    hard_reasons = sorted(reasons)

    base["status"] = (
        "PASS"
        if not hard_reasons
        else "BLOCKED"
    )

    base["blocked_reasons"] = (
        hard_reasons
    )

    base["source_preserving"] = True

    base["source_preserving_relaxed_reasons"] = sorted(
        original_reasons
        & SOURCE_PRESERVING_RELAXED_REASONS
    )

    base["template_hits"] = (
        template_hits
    )

    base["conversational_ending_count"] = (
        ending_count
    )

    if not hard_reasons:
        account_fit = dict(
            base.get(
                "account_fit_check",
                {},
            )
        )

        account_fit["status"] = "PASS"

        account_fit[
            "source_preserving_override"
        ] = True

        base["account_fit_check"] = (
            account_fit
        )

    return base


class DeterministicSourceCopyeditProvider:
    """Fail-closed fallback that edits only the approved source text."""

    provider_name = (
        "deterministic_source_copyedit"
    )

    provider_version = "1"

    def generate(
        self,
        post: SourcePostBundle,
        *,
        account_id: str,
        recent_posts: list[str],
        transcript_excerpt: str = "",
    ) -> ProviderResult[
        dict[str, Any]
    ]:
        del transcript_excerpt

        source = clean_source_post_text(
            post.original_post_text,
            account_id,
        )

        if not source_text_is_usable(
            source
        ):
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=(
                    "source_post_text_unusable"
                ),
            )

        contract = (
            evaluate_source_copyedit_contract(
                source_text=source,
                public_post_text=source,
                account_id=account_id,
                recent_posts=recent_posts,
            )
        )

        if contract["status"] != "PASS":
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "BLOCKED",
                reason=",".join(
                    contract[
                        "blocked_reasons"
                    ]
                ),
                metadata={
                    "source_preservation_similarity": (
                        contract[
                            "source_preservation_similarity"
                        ]
                    ),
                    "recent_post_similarity": (
                        contract[
                            "recent_post_similarity"
                        ]
                    ),
                },
            )

        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data={
                "internal_analysis": {
                    "main_claims": [
                        source
                    ],
                    "topic": (
                        "source_copyedit"
                    ),
                    "audience": (
                        account_id
                    ),
                    "copyedit_strategy": (
                        "preserve_source_then_polish"
                    ),
                    "media_role": (
                        "same_parent_direct_media"
                    ),
                },
                "public_post_text": source,
                "claim_support": [
                    {
                        "caption_claim": (
                            source
                        ),
                        "source_evidence": (
                            source
                        ),
                    }
                ],
                "safety_notes": (
                    "Approved source text was "
                    "sanitized without adding "
                    "new claims."
                ),
                "blocked_reasons": [],
                "source_copyedit_contract": (
                    contract
                ),
            },
            metadata={
                "source_preservation_similarity": (
                    contract[
                        "source_preservation_similarity"
                    ]
                ),
                "recent_post_similarity": (
                    contract[
                        "recent_post_similarity"
                    ]
                ),
            },
        )
