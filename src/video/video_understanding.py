"""
video_understanding.py - Video Understanding / Clip Candidate Planner（Phase 9）

transcript / title / description / metadata から動画内容を理解し、
clip_candidates / hook_candidates / generated_post_copy を生成する。

実download/実cut/実upload禁止。すべてplan/dry-run。
transcriptがない場合はmetadataベースで仮プラン。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _short_id() -> str:
    return str(uuid.uuid4())[:8]


class VideoUnderstanding:
    """動画の内容理解とクリップ候補プランを生成する。

    download/cut/upload は一切行わない。すべてプランのみ。
    """

    def analyze(
        self,
        item: dict[str, Any],
        *,
        account_id: str = "",
        target_platform: str = "threads",
        mock: bool = True,
    ) -> dict[str, Any]:
        """raw_source_item (dict) から動画理解結果を返す。"""
        title = item.get("title", "")
        description = item.get("description", "")
        transcript = item.get("transcript", "")
        duration = item.get("duration_seconds")
        view_count = item.get("view_count", 0)
        like_count = item.get("like_count", 0)
        post_url = item.get("post_url", "")
        platform = item.get("source_platform", "youtube")

        has_transcript = bool(transcript)

        if mock:
            return self._mock_analysis(
                item, account_id, target_platform, has_transcript
            )

        # メタデータのみの場合
        if not has_transcript:
            return self._metadata_based_plan(
                title, description, duration, view_count, like_count,
                post_url, platform, account_id, target_platform,
                item.get("source_id", ""),
            )

        return self._transcript_based_analysis(
            title, description, transcript, duration,
            view_count, like_count, post_url, platform,
            account_id, target_platform,
            item.get("source_id", ""),
        )

    def _transcript_based_analysis(
        self,
        title: str,
        description: str,
        transcript: str,
        duration: float | None,
        view_count: int,
        like_count: int,
        post_url: str,
        platform: str,
        account_id: str,
        target_platform: str,
        source_id: str,
    ) -> dict[str, Any]:
        # transcript から key_points を抽出（実際はLLM処理、ここではテキスト分割）
        sentences = [s.strip() for s in transcript.replace("。", "。\n").splitlines() if s.strip()]
        key_points = sentences[:5]

        # hook_candidates: 最初の1-2文が最も有力
        hook_candidates = [
            {"text": s, "confidence": 0.8 - i * 0.1, "reason": f"冒頭{i+1}文目"}
            for i, s in enumerate(sentences[:3])
        ]

        # clip_candidates: duration がある場合に時間分割
        clip_candidates = []
        if duration and duration > 30:
            segment_count = min(3, int(duration // 30))
            for i in range(segment_count):
                start = i * (duration / segment_count)
                end = (i + 1) * (duration / segment_count)
                clip_candidates.append({
                    "clip_id": f"clip_{_short_id()}",
                    "start_sec": round(start, 1),
                    "end_sec": round(end, 1),
                    "estimated_duration": round(end - start, 1),
                    "label": f"セクション{i+1}",
                    "summary": sentences[i * 2] if i * 2 < len(sentences) else "",
                    "status": "PLAN",
                    "download_required": False,
                    "cut_required": False,
                })

        summary = f"{title}: {' / '.join(key_points[:3])}" if key_points else title

        generated_post = self._generate_post_copy(
            title=title,
            key_points=key_points,
            hook=hook_candidates[0]["text"] if hook_candidates else title,
            target_platform=target_platform,
            account_id=account_id,
        )

        generated_thread = self._generate_thread_copy(
            title=title,
            key_points=key_points,
            target_platform=target_platform,
        )

        return {
            "understanding_id": f"vu_{_short_id()}",
            "source_id": source_id,
            "post_url": post_url,
            "platform": platform,
            "target_account_id": account_id,
            "target_platform": target_platform,
            "title": title,
            "summary": summary,
            "has_transcript": True,
            "key_points": key_points,
            "hook_candidates": hook_candidates,
            "clip_candidates": clip_candidates,
            "recommended_time_ranges": [
                {"start": c["start_sec"], "end": c["end_sec"], "reason": c["label"]}
                for c in clip_candidates
            ],
            "generated_post_copy": generated_post,
            "generated_thread_copy": generated_thread,
            "generation_job_candidate": {
                "type": "video_clip_reference",
                "status": "PLANNED",
                "source_post_url": post_url,
                "clip_candidates": len(clip_candidates),
            },
            "media_ingestion_plan": {
                "action": "plan_only",
                "download_required": False,
                "cut_required": False,
                "upload_required": False,
                "note": "実行には --confirm-download --confirm-cut が必要です",
            },
            "analyzed_at": _now_jst(),
            "status": "OK",
        }

    def _metadata_based_plan(
        self,
        title: str,
        description: str,
        duration: float | None,
        view_count: int,
        like_count: int,
        post_url: str,
        platform: str,
        account_id: str,
        target_platform: str,
        source_id: str,
    ) -> dict[str, Any]:
        hook_candidates = [
            {
                "text": f"「{title}」から学んだこと",
                "confidence": 0.5,
                "reason": "タイトルベース hook",
            }
        ]
        if description:
            hook_candidates.append({
                "text": description[:60],
                "confidence": 0.4,
                "reason": "説明文から抽出",
            })

        generated_post = self._generate_post_copy(
            title=title,
            key_points=[description[:100]] if description else [title],
            hook=title,
            target_platform=target_platform,
            account_id=account_id,
        )

        return {
            "understanding_id": f"vu_{_short_id()}",
            "source_id": source_id,
            "post_url": post_url,
            "platform": platform,
            "target_account_id": account_id,
            "target_platform": target_platform,
            "title": title,
            "summary": f"[transcript なし] {title}",
            "has_transcript": False,
            "key_points": [description[:200]] if description else [],
            "hook_candidates": hook_candidates,
            "clip_candidates": [],
            "recommended_time_ranges": [],
            "generated_post_copy": generated_post,
            "generated_thread_copy": None,
            "generation_job_candidate": {
                "type": "video_reference_no_transcript",
                "status": "WAITING_REVIEW",
                "note": "transcript 取得後に再実行を推奨",
            },
            "media_ingestion_plan": {
                "action": "plan_only",
                "download_required": False,
                "transcript_required": True,
                "note": "transcript 取得には youtube_transcript_fetcher を使用",
            },
            "analyzed_at": _now_jst(),
            "status": "NOT_READY_TRANSCRIPT",
        }

    def _generate_post_copy(
        self,
        title: str,
        key_points: list[str],
        hook: str,
        target_platform: str,
        account_id: str,
    ) -> dict[str, Any]:
        points_text = "\n".join(f"・{p[:60]}" for p in key_points[:3])
        body = f"""【{title}】

{hook[:80]}

{points_text}

詳しくは動画をチェック👇"""

        return {
            "platform": target_platform,
            "account_id": account_id,
            "draft_text": body[:500],
            "char_count": len(body),
            "status": "DRAFT",
            "source": "video_understanding",
            "note": "LLMによる精緻化前の下書き。生成前に必ずレビューしてください。",
        }

    def _generate_thread_copy(
        self,
        title: str,
        key_points: list[str],
        target_platform: str,
    ) -> list[dict[str, Any]] | None:
        if not key_points:
            return None

        thread = [
            {
                "position": 1,
                "text": f"【{title}】について重要なことをまとめました🧵",
                "status": "DRAFT",
            }
        ]
        for i, point in enumerate(key_points[:4], 2):
            thread.append({
                "position": i,
                "text": f"{i-1}/ {point[:100]}",
                "status": "DRAFT",
            })
        thread.append({
            "position": len(key_points) + 2,
            "text": "以上です。参考になったらフォローお願いします！",
            "status": "DRAFT",
        })

        return thread

    def _mock_analysis(
        self,
        item: dict,
        account_id: str,
        target_platform: str,
        has_transcript: bool,
    ) -> dict[str, Any]:
        title = item.get("title", "モック動画タイトル")
        return {
            "understanding_id": f"vu_mock_{_short_id()}",
            "source_id": item.get("source_id", ""),
            "post_url": item.get("post_url", ""),
            "platform": item.get("source_platform", "youtube"),
            "target_account_id": account_id,
            "target_platform": target_platform,
            "title": title,
            "summary": f"[MOCK] {title} のまとめ",
            "has_transcript": has_transcript,
            "key_points": [
                f"重要ポイント1: {title}から学べること",
                "重要ポイント2: 実践方法",
                "重要ポイント3: 次のアクション",
            ],
            "hook_candidates": [
                {"text": f"「{title}」で知っておくべき3つのこと", "confidence": 0.85, "reason": "hook_mock"},
                {"text": f"これを知らないと損する: {title}のポイント", "confidence": 0.75, "reason": "hook_mock_2"},
            ],
            "clip_candidates": [
                {
                    "clip_id": f"clip_mock_{i}",
                    "start_sec": i * 30.0,
                    "end_sec": (i + 1) * 30.0,
                    "estimated_duration": 30.0,
                    "label": f"セクション{i+1}",
                    "status": "PLAN",
                    "download_required": False,
                    "cut_required": False,
                }
                for i in range(3)
            ],
            "generated_post_copy": {
                "platform": target_platform,
                "account_id": account_id,
                "draft_text": f"【モック下書き】{title}\n\n重要ポイントを3つ紹介します。\n・ポイント1\n・ポイント2\n・ポイント3",
                "status": "DRAFT",
                "source": "mock_video_understanding",
            },
            "generated_thread_copy": [
                {"position": 1, "text": f"【{title}】について", "status": "DRAFT"},
                {"position": 2, "text": "1/ 重要ポイント1の詳細説明", "status": "DRAFT"},
                {"position": 3, "text": "2/ 重要ポイント2の詳細説明", "status": "DRAFT"},
            ],
            "generation_job_candidate": {
                "type": "video_clip_reference",
                "status": "PLANNED",
            },
            "media_ingestion_plan": {
                "action": "plan_only",
                "download_required": False,
                "cut_required": False,
                "upload_required": False,
            },
            "analyzed_at": _now_jst(),
            "status": "OK",
            "mock": True,
        }
