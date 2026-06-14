"""
source_to_post_orchestrator.py - Source → Post End-to-End Orchestrator（Phase 11）

指定source → buzz抽出 → reference_posts → media/video plan
→ generation_jobs → draft/thread_series → preflight → publish plan → PDCA候補

安全方針:
  - fetch confirmなし: 取得BLOCKED
  - download confirmなし: download BLOCKED
  - post confirmなし: publish BLOCKED
  - beauty_account: WAITING_REVIEW/BLOCKED維持
  - 実投稿なし / 実downloadなし / secret表示なし
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _new_run_id() -> str:
    return f"s2p_{str(uuid.uuid4())[:8]}"


class SourceToPostOrchestrator:
    """Source-to-Post パイプライン全体を協調するオーケストレーター。"""

    def run(
        self,
        *,
        account_id: str,
        platform: str,
        source_id: str | None = None,
        source_platform: str | None = None,
        generation_mode: str | None = None,
        mock: bool = True,
        dry_run: bool = True,
        confirm_fetch: bool = False,
        confirm_download: bool = False,
        confirm_post: bool = False,
        max_source_items: int = 10,
        top_n: int = 3,
    ) -> dict[str, Any]:
        run_id = _new_run_id()
        is_beauty = account_id == "beauty_account"
        blocked_reasons: list[str] = []

        # ===== Step 1: Source Fetch =====
        fetch_result = self._step_fetch(
            account_id=account_id,
            platform=platform,
            source_id=source_id,
            source_platform=source_platform,
            mock=mock,
            dry_run=dry_run,
            confirm_fetch=confirm_fetch,
            max_items=max_source_items,
        )
        if fetch_result["status"] == "BLOCKED":
            blocked_reasons.append(f"fetch: {fetch_result['message']}")

        # ===== Step 2: Buzz Scoring =====
        buzz_result = self._step_buzz_score(
            fetch_result=fetch_result,
            mock=mock,
            top_n=top_n,
        )

        # ===== Step 3: Reference Posts =====
        reference_result = self._step_reference_posts(
            buzz_result=buzz_result,
            account_id=account_id,
            mock=mock,
        )

        # ===== Step 4: Media / Video Plan =====
        media_result = self._step_media_plan(
            reference_result=reference_result,
            confirm_download=confirm_download,
            mock=mock,
        )
        if not confirm_download and media_result.get("download_candidates"):
            blocked_reasons.append("download: --confirm-download が必要です")

        # ===== Step 5: Generation Jobs =====
        generation_result = self._step_generation(
            reference_result=reference_result,
            account_id=account_id,
            platform=platform,
            generation_mode=generation_mode,
            is_beauty=is_beauty,
            mock=mock,
            dry_run=dry_run,
        )

        # ===== Step 6: Preflight =====
        preflight_result = self._step_preflight(
            generation_result=generation_result,
            account_id=account_id,
            platform=platform,
            is_beauty=is_beauty,
            confirm_post=confirm_post,
        )
        if not confirm_post:
            blocked_reasons.append("publish: --confirm-post が必要です")

        # ===== Step 7: Publish Plan =====
        publish_result = self._step_publish_plan(
            preflight_result=preflight_result,
            account_id=account_id,
            platform=platform,
            is_beauty=is_beauty,
            confirm_post=confirm_post,
        )

        # ===== Step 8: PDCA Candidates =====
        pdca_result = self._step_pdca_candidates(
            fetch_result=fetch_result,
            buzz_result=buzz_result,
            generation_result=generation_result,
            account_id=account_id,
        )

        overall_status = "BLOCKED" if blocked_reasons else ("OK" if not is_beauty else "WAITING_REVIEW")

        return {
            "run_id": run_id,
            "account_id": account_id,
            "platform": platform,
            "source_id": source_id,
            "source_platform": source_platform,
            "generation_mode": generation_mode,
            "mock": mock,
            "dry_run": dry_run,
            "is_beauty": is_beauty,
            "status": overall_status,
            "blocked_reasons": blocked_reasons,
            "steps": {
                "fetch": fetch_result,
                "buzz_score": buzz_result,
                "reference_posts": reference_result,
                "media_plan": media_result,
                "generation": generation_result,
                "preflight": preflight_result,
                "publish_plan": publish_result,
                "pdca_candidates": pdca_result,
            },
            "summary": {
                "fetched_items": fetch_result.get("item_count", 0),
                "top_buzz_items": buzz_result.get("top_item_count", 0),
                "reference_posts": reference_result.get("reference_count", 0),
                "draft_count": generation_result.get("draft_count", 0),
                "preflight_status": preflight_result.get("status", "UNKNOWN"),
                "publish_blocked": not confirm_post,
            },
            "safety": {
                "real_fetch": confirm_fetch,
                "real_download": confirm_download,
                "real_post": confirm_post,
                "beauty_account_blocked": is_beauty,
                "no_real_download": True,
                "no_real_post": True,
            },
            "executed_at": _now_jst(),
        }

    # ---- Step implementations ----

    def _step_fetch(
        self,
        account_id: str,
        platform: str,
        source_id: str | None,
        source_platform: str | None,
        mock: bool,
        dry_run: bool,
        confirm_fetch: bool,
        max_items: int,
    ) -> dict[str, Any]:
        if not mock and not confirm_fetch:
            return {
                "status": "BLOCKED",
                "message": "--confirm-fetch なしの実取得はBLOCKEDです。",
                "item_count": 0,
                "items": [],
            }

        if mock:
            _sp = source_platform or "youtube"
            mock_items = [
                {
                    "raw_item_id": f"mock_{i:03d}",
                    "source_id": source_id or f"src_{account_id}",
                    "source_platform": _sp,
                    "target_account_id": account_id,
                    "fetch_adapter": "mock",
                    "item_type": "video" if _sp in ("youtube", "tiktok") else "post",
                    "post_url": f"https://{_sp}.com/mock/{i}",
                    "text": f"【MOCK】参考投稿 #{i+1}",
                    "title": f"モック動画 #{i+1}",
                    "like_count": 1000 * (i + 1),
                    "view_count": 10000 * (i + 1),
                    "reply_count": 50 * (i + 1),
                    "repost_count": 100 * (i + 1),
                    "mock": True,
                }
                for i in range(min(3, max_items))
            ]
            return {
                "status": "OK",
                "item_count": len(mock_items),
                "items": mock_items,
                "mock": True,
            }

        # 実取得は fetcher_registry 経由
        try:
            from ..reference.fetchers.fetcher_registry import FetcherRegistry
            from ..reference.source_registry import load_sources

            registry = FetcherRegistry()
            sources = load_sources()
            target_sources = [
                s for s in sources
                if (not source_id or s.get("source_id") == source_id)
                and (not source_platform or s.get("source_platform") == source_platform)
                and s.get("active", True)
                and not s.get("blocked", False)
            ]

            all_items = []
            for src in target_sources[:3]:
                fetcher = registry.get(
                    src.get("collection_method", "manual_json"),
                    src.get("source_platform", ""),
                )
                result = fetcher.fetch(
                    src,
                    target_account_id=account_id,
                    mock=False,
                    dry_run=dry_run,
                    confirm_fetch=confirm_fetch,
                    max_items=max_items,
                )
                all_items.extend([i.to_dict() for i in result.items])

            return {
                "status": "OK",
                "item_count": len(all_items),
                "items": all_items,
                "mock": False,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": str(e),
                "item_count": 0,
                "items": [],
            }

    def _step_buzz_score(
        self,
        fetch_result: dict,
        mock: bool,
        top_n: int,
    ) -> dict[str, Any]:
        items = fetch_result.get("items", [])
        if not items:
            return {"status": "NO_DATA", "top_item_count": 0, "items": [], "top_items": []}

        try:
            from ..reference.fetchers.base_fetcher import RawSourceItem
            from ..reference.buzz_scorer import score_items, filter_top_items

            raw_items = [RawSourceItem.from_dict(d) for d in items]
            scored = score_items(raw_items)
            top = filter_top_items(scored, min_buzz_score=0.1, top_n=top_n)

            return {
                "status": "OK",
                "total_item_count": len(scored),
                "top_item_count": len(top),
                "items": [i.to_dict() for i in scored],
                "top_items": [i.to_dict() for i in top],
                "mock": mock,
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "message": str(e),
                "top_item_count": len(items),
                "items": items,
                "top_items": items[:top_n],
            }

    def _step_reference_posts(
        self,
        buzz_result: dict,
        account_id: str,
        mock: bool,
    ) -> dict[str, Any]:
        top_items = buzz_result.get("top_items", [])
        references = []

        for item in top_items:
            ref = {
                "ref_id": f"ref_{str(uuid.uuid4())[:6]}",
                "source_id": item.get("source_id", ""),
                "source_url": item.get("post_url", ""),
                "platform": item.get("source_platform", ""),
                "text": item.get("text", item.get("title", "")),
                "title": item.get("title", ""),
                "buzz_score": item.get("buzz_score"),
                "why_it_grew": item.get("why_it_grew"),
                "replay_tip": item.get("replay_tip"),
                "recommended_generation_mode": item.get("recommended_generation_mode"),
                "has_video": bool(item.get("video_urls") or item.get("item_type") == "video"),
                "has_transcript": bool(item.get("transcript")),
                "image_urls": item.get("image_urls", []),
                "video_urls": item.get("video_urls", []),
                "account_id": account_id,
                "status": "REFERENCE_READY",
                "mock": mock,
            }
            references.append(ref)

        return {
            "status": "OK",
            "reference_count": len(references),
            "references": references,
        }

    def _step_media_plan(
        self,
        reference_result: dict,
        confirm_download: bool,
        mock: bool,
    ) -> dict[str, Any]:
        references = reference_result.get("references", [])
        download_candidates = [r for r in references if r.get("has_video")]

        plan = {
            "status": "OK",
            "download_candidates": len(download_candidates),
            "action": "plan_only",
            "download_blocked": not confirm_download,
            "note": "実downloadには --confirm-download が必要です",
        }

        if download_candidates and not confirm_download:
            plan["status"] = "BLOCKED_DOWNLOAD"

        return plan

    def _step_generation(
        self,
        reference_result: dict,
        account_id: str,
        platform: str,
        generation_mode: str | None,
        is_beauty: bool,
        mock: bool,
        dry_run: bool,
    ) -> dict[str, Any]:
        references = reference_result.get("references", [])
        status = "WAITING_REVIEW" if is_beauty else "PLANNED"
        drafts = []

        for ref in references[:3]:
            mode = generation_mode or ref.get("recommended_generation_mode", "reference_based_text")
            draft = {
                "draft_id": f"draft_{str(uuid.uuid4())[:6]}",
                "account_id": account_id,
                "platform": platform,
                "source_ref_id": ref.get("ref_id", ""),
                "generation_mode": mode,
                "text": f"【{'MOCK ' if mock else ''}下書き】{ref.get('text', '')[:100]}",
                "status": "DRAFT" if not is_beauty else "WAITING_REVIEW",
                "mock": mock,
                "dry_run": dry_run,
            }
            drafts.append(draft)

        return {
            "status": status,
            "draft_count": len(drafts),
            "drafts": drafts,
            "is_beauty": is_beauty,
            "note": "beauty_account は常にWAITING_REVIEW" if is_beauty else "",
        }

    def _step_preflight(
        self,
        generation_result: dict,
        account_id: str,
        platform: str,
        is_beauty: bool,
        confirm_post: bool,
    ) -> dict[str, Any]:
        checks = {
            "has_drafts": generation_result.get("draft_count", 0) > 0,
            "not_beauty_or_waiting_review": not is_beauty,
            "confirm_post": confirm_post,
        }
        passed = checks["has_drafts"] and not is_beauty and confirm_post

        return {
            "status": "PASS" if passed else "BLOCKED",
            "checks": checks,
            "passed": passed,
            "message": (
                "beauty_accountは常にBLOCKED" if is_beauty
                else ("BLOCKED: --confirm-post が必要です" if not confirm_post
                      else ("PASS" if passed else "BLOCKED: draft なし"))
            ),
        }

    def _step_publish_plan(
        self,
        preflight_result: dict,
        account_id: str,
        platform: str,
        is_beauty: bool,
        confirm_post: bool,
    ) -> dict[str, Any]:
        if not confirm_post or is_beauty:
            return {
                "status": "BLOCKED",
                "message": (
                    "beauty_account は自動投稿不可" if is_beauty
                    else "--confirm-post なしの実投稿はBLOCKEDです"
                ),
                "real_post": False,
            }

        return {
            "status": "READY_TO_QUEUE",
            "message": "preflight PASS。publish_queue.py で投稿キューに追加可能です。",
            "real_post": False,
            "note": "実投稿は publish_queue.py + --confirm-post で実行してください",
        }

    def _step_pdca_candidates(
        self,
        fetch_result: dict,
        buzz_result: dict,
        generation_result: dict,
        account_id: str,
    ) -> dict[str, Any]:
        top_items = buzz_result.get("top_items", [])

        source_suggestions = []
        for item in top_items[:2]:
            sp = item.get("source_platform", "")
            source_suggestions.append({
                "type": "source_priority_up",
                "source_platform": sp,
                "reason": f"buzz_score {item.get('buzz_score', 0):.2f} の高品質参考投稿あり",
                "status": "WAITING_REVIEW",
                "auto_apply": False,
            })

        return {
            "status": "OK",
            "next_collection_candidates": source_suggestions,
            "note": "自動反映なし。WAITING_REVIEW で保存し、ユーザーが確認後に反映。",
        }


def run_pipeline(
    account_id: str,
    platform: str,
    *,
    source_id: str | None = None,
    source_platform: str | None = None,
    generation_mode: str | None = None,
    mock: bool = True,
    dry_run: bool = True,
    confirm_fetch: bool = False,
    confirm_download: bool = False,
    confirm_post: bool = False,
    max_source_items: int = 10,
    top_n: int = 3,
) -> dict[str, Any]:
    """SourceToPostOrchestrator の便利ラッパー。"""
    orchestrator = SourceToPostOrchestrator()
    return orchestrator.run(
        account_id=account_id,
        platform=platform,
        source_id=source_id,
        source_platform=source_platform,
        generation_mode=generation_mode,
        mock=mock,
        dry_run=dry_run,
        confirm_fetch=confirm_fetch,
        confirm_download=confirm_download,
        confirm_post=confirm_post,
        max_source_items=max_source_items,
        top_n=top_n,
    )
