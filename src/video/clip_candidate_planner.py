"""
clip_candidate_planner.py - Clip Candidate Plan Generator（Phase 9）

video_understanding の結果から clip_candidate_plan を作成する。
実download/実cut/実upload禁止。すべてplan_only。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _new_plan_id() -> str:
    return f"ccp_{str(uuid.uuid4())[:8]}"


class ClipCandidatePlanner:
    """video_understanding 結果から clip_candidate_plan を作成する。"""

    def plan(
        self,
        understanding: dict[str, Any],
        *,
        account_id: str = "",
        target_platform: str = "threads",
        max_clips: int = 5,
        mock: bool = True,
    ) -> dict[str, Any]:
        if mock:
            return self._mock_plan(understanding, account_id, target_platform)

        clip_candidates = understanding.get("clip_candidates", [])
        if not clip_candidates:
            return {
                "plan_id": _new_plan_id(),
                "status": "NO_CLIPS",
                "message": "clip_candidates が空です。transcript 取得または動画URLを確認してください。",
                "source_id": understanding.get("source_id", ""),
                "clips": [],
                "created_at": _now_jst(),
            }

        clips = []
        for clip in clip_candidates[:max_clips]:
            post_copy = self._generate_clip_post(
                clip, understanding, target_platform, account_id
            )
            clips.append({
                "clip_id": clip.get("clip_id", f"clip_{str(uuid.uuid4())[:6]}"),
                "start_sec": clip.get("start_sec", 0),
                "end_sec": clip.get("end_sec", 30),
                "duration": clip.get("estimated_duration", 30),
                "label": clip.get("label", ""),
                "summary": clip.get("summary", ""),
                "generated_post_copy": post_copy,
                "media_plan": {
                    "action": "plan_only",
                    "download_required": False,
                    "cut_required": False,
                    "upload_required": False,
                    "note": "実行には --confirm-download --confirm-cut が必要",
                },
                "status": "PLANNED",
            })

        return {
            "plan_id": _new_plan_id(),
            "status": "OK",
            "source_id": understanding.get("source_id", ""),
            "source_url": understanding.get("post_url", ""),
            "target_account_id": account_id,
            "target_platform": target_platform,
            "total_clip_candidates": len(clip_candidates),
            "planned_clips": len(clips),
            "clips": clips,
            "created_at": _now_jst(),
            "note": "すべてplan_only。実cutには confirm が必要。",
        }

    def _generate_clip_post(
        self,
        clip: dict,
        understanding: dict,
        target_platform: str,
        account_id: str,
    ) -> dict[str, Any]:
        title = understanding.get("title", "")
        summary = clip.get("summary", title)
        label = clip.get("label", "")

        text = f"""【切り抜き候補: {label}】

{summary[:100]}

元動画: {understanding.get("post_url", "")}"""

        return {
            "platform": target_platform,
            "account_id": account_id,
            "draft_text": text[:500],
            "status": "DRAFT",
            "source": "clip_candidate_planner",
        }

    def _mock_plan(
        self, understanding: dict, account_id: str, target_platform: str
    ) -> dict[str, Any]:
        return {
            "plan_id": _new_plan_id(),
            "status": "OK",
            "source_id": understanding.get("source_id", ""),
            "source_url": understanding.get("post_url", ""),
            "target_account_id": account_id,
            "target_platform": target_platform,
            "total_clip_candidates": 3,
            "planned_clips": 3,
            "clips": [
                {
                    "clip_id": f"clip_mock_{i}",
                    "start_sec": i * 30.0,
                    "end_sec": (i + 1) * 30.0,
                    "duration": 30.0,
                    "label": f"セクション{i+1}",
                    "generated_post_copy": {
                        "platform": target_platform,
                        "account_id": account_id,
                        "draft_text": f"【モック切り抜き{i+1}】セクション{i+1}のハイライトです",
                        "status": "DRAFT",
                    },
                    "media_plan": {"action": "plan_only", "download_required": False},
                    "status": "PLANNED",
                }
                for i in range(3)
            ],
            "created_at": _now_jst(),
            "mock": True,
        }
