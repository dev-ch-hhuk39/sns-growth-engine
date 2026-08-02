#!/usr/bin/env python3
"""Build the final ten-slot route-level canary plan.

This command never reads credentials, mutates Sheets,
fetches media, uploads media, or posts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
    TEXT_ACTIVATION_CANARY_TYPES,
    activation_canary_id,
    canonical_activation_type,
)

CANARY_TYPES = ACTIVATION_CANARY_TYPES
FIRST_WAVE_TYPES = (
    "original_text",
    "direct_reference_media",
)

QUALITY_GATE_VERSION = (
    "generation_quality_v3"
)
TOPIC_CONFIDENCE_MIN = 0.70


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "pass",
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def _present(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, list):
        return bool(value)

    return True


def required_fields(
    canary_type: str,
) -> tuple[str, ...]:
    quality = (
        "batch_id",
        "batch_diversity_status",
        "topic_coherence_status",
        "primary_topic",
        "topic_confidence",
        "structure_variant",
        "hook_topic_match",
        "closing_topic_match",
        "quality_gate_version",
    )

    if canary_type in (
        TEXT_ACTIVATION_CANARY_TYPES
    ):
        return (
            "account_id",
            "public_post_text",
            "queue_id",
            "persona_validator_status",
            (
                "final_public_post_"
                "validator_status"
            ),
            "internal_leak_status",
        ) + quality

    common = (
        "account_id",
        "source_id",
        "rights_status",
        "permission_status",
        "permission_evidence",
        "public_post_text",
    )

    validated_media = (
        "queue_id",
        "persona_validator_status",
        (
            "final_public_post_"
            "validator_status"
        ),
        "internal_leak_status",
        "publisher_media_type",
        "alignment_status",
        "final_alignment_score",
        "main_claim_coverage",
        "unsupported_claim_count",
        "source_copy_similarity",
        "recent_post_similarity",
        "feature_schema_version",
        "media_primary_topic",
        "visual_topic",
        "visual_topic_match",
        "visual_cta_match",
        "visual_plan_version",
        "visual_text_hash",
        "claim_support_json",
    ) + quality

    if (
        canary_type
        == "approved_source_clip"
    ):
        return (
            common
            + validated_media
            + (
                "source_video_id",
                "clip_candidate_id",
                "local_path",
                "start_seconds",
                "end_seconds",
            )
        )

    return (
        common
        + validated_media
        + (
            "source_post_id",
        )
    )


def _has_direct_media_payload(
    candidate: dict[str, Any],
) -> bool:
    single = bool(
        str(
            candidate.get(
                "media_asset_id",
                "",
            )
        ).strip()
        and str(
            candidate.get(
                "media_url",
                "",
            )
        ).strip()
    )

    multiple = (
        isinstance(
            candidate.get(
                "media_asset_ids",
            ),
            list,
        )
        and bool(
            candidate.get(
                "media_asset_ids"
            )
        )
        and isinstance(
            candidate.get(
                "media_urls",
            ),
            list,
        )
        and bool(
            candidate.get(
                "media_urls"
            )
        )
    )

    return single or multiple


def build_plan(
    candidates: list[dict[str, Any]],
    *,
    wave: str = "all_10",
) -> dict[str, Any]:
    if wave == "all_12":
        wave = "all_10"

    if wave not in {
        "all_10",
        "first_wave",
    }:
        raise ValueError(
            "unsupported_wave"
        )

    selected_types = (
        FIRST_WAVE_TYPES
        if wave == "first_wave"
        else CANARY_TYPES
    )

    relevant: list[
        dict[str, Any]
    ] = []

    for source in candidates:
        row = dict(source)

        kind = canonical_activation_type(
            row.get(
                "canary_type",
                "",
            ),
            content_route=row.get(
                "content_route",
                "",
            ),
        )

        account_id = str(
            row.get(
                "account_id",
                "",
            )
        )

        if (
            kind not in selected_types
            or account_id not in ACCOUNTS
        ):
            continue

        row["canary_type"] = kind
        relevant.append(row)

    batch_ids = {
        str(
            row.get(
                "batch_id",
                "",
            )
        ).strip()
        for row in relevant
        if str(
            row.get(
                "batch_id",
                "",
            )
        ).strip()
    }

    same_batch_ok = (
        wave != "first_wave"
        or (
            len(relevant) == 4
            and len(batch_ids) == 1
        )
    )

    by_key = {
        (
            str(
                row.get(
                    "account_id",
                    "",
                )
            ),
            str(
                row.get(
                    "canary_type",
                    "",
                )
            ),
        ): row
        for row in relevant
    }

    rows: list[dict[str, Any]] = []

    for account_id in ACCOUNTS:
        for canary_type in (
            selected_types
        ):
            candidate = dict(
                by_key.get(
                    (
                        account_id,
                        canary_type,
                    ),
                    {},
                )
            )

            required = required_fields(
                canary_type
            )

            missing = [
                field
                for field in required
                if not _present(
                    candidate.get(field)
                )
            ]

            if (
                canary_type
                == "direct_reference_media"
                and not _has_direct_media_payload(
                    candidate
                )
            ):
                missing.append(
                    "direct_media_payload"
                )

            is_text = (
                canary_type
                in TEXT_ACTIVATION_CANARY_TYPES
            )

            rights_ok = (
                is_text
                or str(
                    candidate.get(
                        "rights_status",
                        "",
                    )
                )
                in {
                    "owned",
                    "licensed",
                    (
                        "approved_creator_"
                        "clip"
                    ),
                }
            )

            permission_ok = (
                is_text
                or str(
                    candidate.get(
                        "permission_status",
                        "",
                    )
                )
                == "approved"
            )

            validators_ok = all(
                str(
                    candidate.get(
                        field,
                        "",
                    )
                ).upper()
                == "PASS"
                for field in (
                    (
                        "persona_"
                        "validator_status"
                    ),
                    (
                        "final_public_post_"
                        "validator_status"
                    ),
                    "internal_leak_status",
                )
            )

            alignment_ok = (
                is_text
                or (
                    str(
                        candidate.get(
                            "alignment_status",
                            "",
                        )
                    ).upper()
                    == "PASS"
                    and _as_bool(
                        candidate.get(
                            "visual_topic_match"
                        )
                    )
                    and _as_bool(
                        candidate.get(
                            "visual_cta_match"
                        )
                    )
                    and _as_float(
                        candidate.get(
                            "main_claim_coverage"
                        )
                    )
                    >= 1.0
                    and int(
                        _as_float(
                            candidate.get(
                                (
                                    "unsupported_"
                                    "claim_count"
                                )
                            )
                        )
                    )
                    == 0
                    and str(
                        candidate.get(
                            (
                                "feature_schema_"
                                "version"
                            ),
                            "",
                        )
                    )
                    == "post_features_v1"
                    and str(
                        candidate.get(
                            (
                                "visual_plan_"
                                "version"
                            ),
                            "",
                        )
                    )
                    == "visual_plan_v1"
                )
            )

            quality_ok = (
                str(
                    candidate.get(
                        (
                            "batch_diversity_"
                            "status"
                        ),
                        "",
                    )
                ).upper()
                == "PASS"
                and str(
                    candidate.get(
                        (
                            "topic_coherence_"
                            "status"
                        ),
                        "",
                    )
                ).upper()
                == "PASS"
                and str(
                    candidate.get(
                        (
                            "quality_gate_"
                            "version"
                        ),
                        "",
                    )
                )
                == QUALITY_GATE_VERSION
                and _as_float(
                    candidate.get(
                        "topic_confidence"
                    )
                )
                >= TOPIC_CONFIDENCE_MIN
                and _as_bool(
                    candidate.get(
                        "hook_topic_match"
                    )
                )
                and _as_bool(
                    candidate.get(
                        "closing_topic_match"
                    )
                )
                and not _as_bool(
                    candidate.get(
                        "shared_hook_detected"
                    )
                )
                and not _as_bool(
                    candidate.get(
                        (
                            "shared_closing_"
                            "detected"
                        )
                    )
                )
            )

            ready = (
                bool(candidate)
                and not missing
                and rights_ok
                and permission_ok
                and validators_ok
                and alignment_ok
                and quality_ok
                and same_batch_ok
            )

            rows.append(
                {
                    "canary_id": str(
                        candidate.get(
                            "canary_id"
                        )
                        or activation_canary_id(
                            account_id,
                            canary_type,
                        )
                    ),
                    "batch_id": str(
                        candidate.get(
                            "batch_id",
                            "",
                        )
                    ),
                    "account_id": (
                        account_id
                    ),
                    "canary_type": (
                        canary_type
                    ),
                    "status": (
                        (
                            "READY_FOR_"
                            "HUMAN_CANARY"
                        )
                        if ready
                        else (
                            "PENDING_"
                            "EVIDENCE"
                        )
                    ),
                    "missing_evidence": (
                        missing
                        + (
                            []
                            if rights_ok
                            else [
                                (
                                    "approved_"
                                    "rights_status"
                                )
                            ]
                        )
                        + (
                            []
                            if permission_ok
                            else [
                                (
                                    "permission_"
                                    "status=approved"
                                )
                            ]
                        )
                        + (
                            []
                            if validators_ok
                            else [
                                (
                                    "media_"
                                    "validators=PASS"
                                )
                            ]
                        )
                        + (
                            []
                            if alignment_ok
                            else [
                                (
                                    "alignment_"
                                    "status=PASS"
                                )
                            ]
                        )
                        + (
                            []
                            if quality_ok
                            else [
                                (
                                    "generation_"
                                    "quality_gates="
                                    "PASS"
                                )
                            ]
                        )
                        + (
                            []
                            if same_batch_ok
                            else [
                                (
                                    "exact_four_"
                                    "same_batch_"
                                    "required"
                                )
                            ]
                        )
                    ),
                    "publish_limit": 1,
                    "required_read_after_write": [
                        "Threads post URL",
                        (
                            "posted_results "
                            "result_id"
                        ),
                        (
                            "media asset "
                            "provenance"
                        ),
                        (
                            "metrics "
                            "24h/72h/7d jobs"
                        ),
                    ],
                    "rollback": (
                        "set kill_switch=true; "
                        "preserve posted result; "
                        "do not retry the same "
                        "idempotency key"
                    ),
                }
            )

    ready_count = sum(
        row["status"]
        == "READY_FOR_HUMAN_CANARY"
        for row in rows
    )

    return {
        "status": "PLAN_ONLY",
        "wave": wave,
        "selected_batch_id": (
            next(
                iter(batch_ids),
                "",
            )
            if len(batch_ids) == 1
            else ""
        ),
        "same_batch_contract": (
            "PASS"
            if same_batch_ok
            else "BLOCKED"
        ),
        "total_canaries": len(rows),
        "ready_canaries": ready_count,
        "accounts": list(ACCOUNTS),
        "canaries": rows,
        "would_fetch": False,
        "would_write": False,
        "would_upload": False,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--input-json",
        default="",
    )

    parser.add_argument(
        "--wave",
        choices=[
            "all_10",
            "all_12",
            "first_wave",
        ],
        default="all_10",
    )

    args = parser.parse_args()

    candidates: list[
        dict[str, Any]
    ] = []

    if args.input_json:
        candidates = list(
            json.loads(
                Path(
                    args.input_json
                ).read_text(
                    encoding="utf-8"
                )
            ).get(
                "candidates",
                [],
            )
        )

    print(
        json.dumps(
            build_plan(
                candidates,
                wave=args.wave,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
