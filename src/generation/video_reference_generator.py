"""
video_reference_generator.py - Video Reference based Post Generator（Phase 9/10）

video_understanding の結果を元に投稿/スレッドを生成する。
実download/実upload禁止。すべてdraft/plan。
beauty_account は WAITING_REVIEW 固定。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .reference_source_rewriter import ReferenceRewriteError, rewrite_reference_post

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


class VideoReferenceGenerator:
    """video_understanding 結果から投稿案を生成する。"""

    def generate(
        self,
        understanding: dict[str, Any],
        *,
        account_id: str = "",
        target_platform: str = "threads",
        generation_mode: str = "video_clip_reference",
        mock: bool = True,
    ) -> dict[str, Any]:
        is_beauty = account_id == "beauty_account"
        status = "WAITING_REVIEW" if is_beauty else "PLANNED"
        has_transcript = bool(understanding.get("has_transcript"))
        clip_candidates = list(understanding.get("clip_candidates") or [])

        if mock:
            return self._mock_result(understanding, account_id, target_platform, status)

        platform = str(understanding.get("platform") or "").lower()
        semantic_ready = understanding.get("semantic_ready")
        if semantic_ready is None:
            if platform in {"youtube", "youtube_shorts", "tiktok"}:
                semantic_ready = has_transcript
            else:
                semantic_ready = bool(understanding.get("source_text") or understanding.get("transcript"))
        if not semantic_ready:
            return {
                "job_id": f"vrg_{str(uuid.uuid4())[:8]}",
                "source_id": understanding.get("source_id", ""),
                "source_url": understanding.get("post_url", ""),
                "account_id": account_id,
                "target_platform": target_platform,
                "generation_mode": generation_mode,
                "has_transcript": has_transcript,
                "status": "WAITING_REVIEW",
                "is_beauty": is_beauty,
                "draft_count": 0,
                "drafts": [],
                "clip_plan_count": len(clip_candidates),
                "blocked_reason": understanding.get("semantic_block_reason") or "semantic_source_not_ready",
                "created_at": _now_jst(),
            }

        try:
            rewritten = rewrite_reference_post(
                account_id=account_id,
                source=understanding,
                source_score={},
                target_platform=target_platform,
                slot_theme=generation_mode,
            )
        except ReferenceRewriteError as exc:
            return {
                "job_id": f"vrg_{str(uuid.uuid4())[:8]}",
                "source_id": understanding.get("source_id", ""),
                "source_url": understanding.get("post_url", ""),
                "account_id": account_id,
                "target_platform": target_platform,
                "generation_mode": generation_mode,
                "has_transcript": has_transcript,
                "status": "WAITING_REVIEW",
                "is_beauty": is_beauty,
                "draft_count": 0,
                "drafts": [],
                "clip_plan_count": len(clip_candidates),
                "blocked_reason": str(exc),
                "created_at": _now_jst(),
            }

        post_text = str(rewritten["public_post_text"]).strip()
        drafts = [{
            "draft_id": f"vrd_{str(uuid.uuid4())[:6]}",
            "type": "text_post",
            "platform": target_platform,
            "account_id": account_id,
            "text": post_text,
            "char_count": len(post_text),
            "status": "DRAFT",
            "generation_mode": generation_mode,
            "generation_model": rewritten.get("generation_model", ""),
            "generation_strategy": rewritten.get("generation_strategy", "source_grounded_gemini_v1"),
            "semantic_fidelity": rewritten.get("semantic_fidelity", {}),
        }]
        return {
            "job_id": f"vrg_{str(uuid.uuid4())[:8]}",
            "source_id": understanding.get("source_id", ""),
            "source_url": understanding.get("post_url", ""),
            "account_id": account_id,
            "target_platform": target_platform,
            "generation_mode": generation_mode,
            "has_transcript": has_transcript,
            "status": status,
            "is_beauty": is_beauty,
            "draft_count": len(drafts),
            "drafts": drafts,
            "clip_plan_count": len(clip_candidates),
            "semantic_fidelity": rewritten.get("semantic_fidelity", {}),
            "generation_model": rewritten.get("generation_model", ""),
            "created_at": _now_jst(),
        }

    def _build_post(
        self,
        title: str,
        hook: str,
        key_points: list[str],
        source_url: str,
        target_platform: str,
    ) -> str:
        points = "\n".join(f"・{p[:50]}" for p in key_points[:3])
        text = f"""{hook}

{points}

元動画を参考に作成しました。"""
        return text[:500]

    def _build_thread(
        self, title: str, hook: str, key_points: list[str], platform: str
    ) -> list[dict]:
        thread = [
            {"position": 1, "text": f"🧵 {hook}", "status": "DRAFT"},
        ]
        for i, point in enumerate(key_points[:4], 2):
            thread.append({"position": i, "text": f"{i-1}/ {point[:100]}", "status": "DRAFT"})
        thread.append({"position": len(key_points) + 2, "text": "以上です！参考になれば♪", "status": "DRAFT"})
        return thread

    def _mock_result(
        self,
        understanding: dict,
        account_id: str,
        target_platform: str,
        status: str,
    ) -> dict[str, Any]:
        title = understanding.get("title", "モック動画")
        return {
            "job_id": f"vrg_mock_{str(uuid.uuid4())[:6]}",
            "source_id": understanding.get("source_id", ""),
            "source_url": understanding.get("post_url", ""),
            "account_id": account_id,
            "target_platform": target_platform,
            "generation_mode": "mock_video_reference",
            "has_transcript": understanding.get("has_transcript", False),
            "status": status,
            "is_beauty": account_id == "beauty_account",
            "draft_count": 2,
            "drafts": [
                {
                    "draft_id": "mock_vrd_001",
                    "type": "text_post",
                    "platform": target_platform,
                    "account_id": account_id,
                    "text": f"【MOCK】{title}\n\n重要ポイント1\n重要ポイント2\n重要ポイント3",
                    "status": "DRAFT",
                    "mock": True,
                },
                {
                    "draft_id": "mock_vrd_002",
                    "type": "thread_series",
                    "platform": target_platform,
                    "account_id": account_id,
                    "thread_posts": [
                        {"position": 1, "text": f"🧵 {title} について", "status": "DRAFT"},
                        {"position": 2, "text": "1/ 重要ポイント1", "status": "DRAFT"},
                        {"position": 3, "text": "2/ 重要ポイント2", "status": "DRAFT"},
                    ],
                    "post_count": 3,
                    "status": "DRAFT",
                    "mock": True,
                },
            ],
            "clip_plan_count": 3,
            "created_at": _now_jst(),
            "mock": True,
        }
