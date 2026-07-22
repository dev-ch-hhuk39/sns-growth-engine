"""Deterministic real-shape fixtures for media growth unit tests."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult  # noqa: E402
from generation.source_grounded_caption import SourceGroundedCaptionService  # noqa: E402


class FixtureGroundedCaptionProvider:
    """Return source-supported reader copy without enabling a prod fallback."""

    provider_name = "fixture_grounded_caption"
    provider_version = "1"

    def generate(self, post, *, account_id, recent_posts, transcript_excerpt=""):
        source_text = str(transcript_excerpt or post.original_post_text).strip()
        evidence_rows = [row.strip() for row in re.split(r"[\n]+", source_text) if row.strip()]
        evidence = (evidence_rows[0] if evidence_rows else source_text).strip()
        claim = evidence.rstrip("。！？!?")
        if account_id == "night_scout":
            public_text = (
                "店選びで迷ったときは、目先の時給だけで決めない方がいい。\n\n"
                f"{claim}。\n\n"
                "客層や出勤ペースまで先に確認すると、自分が無理なく続けられる条件が見えやすくなります。"
            )
            audience = "店選びや働き方で迷っている夜職女性"
            topic = "無理なく続けられる店選び"
        else:
            public_text = (
                "配信で初見さんがすぐ離れるときは、面白さより入りやすさを見直した方がいい。\n\n"
                f"{claim}。\n\n"
                "今の話題を短く伝え、最初のコメントを拾う余白を作るだけでも、会話に参加しやすくなります。"
            )
            audience = "配信初心者と伸び悩んでいるライバー"
            topic = "初見が参加しやすい配信設計"
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {
                "core_topic": topic,
                "topic": topic,
                "main_claim": claim,
                "main_claims": [evidence],
                "hook": public_text.splitlines()[0],
                "supporting_points": [claim],
                "concrete_example": "",
                "conclusion": "読者が今日変えられる判断材料を示す",
                "intended_audience": audience,
                "audience": audience,
                "media_role": "source evidence for a text-only caption fixture",
                "factual_constraints": [evidence],
                "prohibited_inferences": ["sourceにない数値や成果を追加しない"],
            },
            "public_post_text": public_text,
            "claim_support": [{"caption_claim": claim, "source_evidence": evidence}],
            "safety_notes": "fixture-private",
            "blocked_reasons": [],
        })


def fixture_caption_service() -> SourceGroundedCaptionService:
    return SourceGroundedCaptionService(FixtureGroundedCaptionProvider())


def liver_video_and_transcript() -> tuple[dict, dict]:
    video = {
        "source_video_id": "sv_src_lm_yt_user_001_abcdefghijk",
        "source_id": "src_lm_yt_user_001",
        "account_id": "liver_manager",
        "platform": "youtube",
        "source_type": "channel",
        "source_url": "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
        "video_id": "abcdefghijk",
        "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "original_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "title": "配信初心者が初見を迎えるときの話し方",
        "description_preview": "初見が入りやすい配信では、入室時の挨拶と今の話題を短く伝えます。",
        "duration_seconds": 60,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "discovery_status": "DISCOVERED",
    }
    transcript = {
        "transcript_id": f"tr_{video['source_video_id']}",
        "source_video_id": video["source_video_id"],
        "transcription_status": "DONE",
        "transcript_text": "配信で初見が入りやすくなるには、入室時の一言と話題の共有が大事です。",
        "segments_json": (
            '[{"start": 1, "end": 12, '
            '"text": "配信で初見が入りやすくなるには入室時の一言が大事です。"}]'
        ),
    }
    return video, transcript
