"""
clip_candidate_analyzer.py - 文字起こしからクリップ候補をGeminiで抽出する

設計:
  - video_transcripts タブの segments_json を入力とする
  - Gemini に 5〜6 件のクリップ候補を JSON で返させる
  - mock_llm=True の場合は固定サンプルを返す（実API呼び出しなし）
  - 権利リスク判定: rights_status / permission_status / media_reuse_risk / imitation_risk
  - 出力は video_clip_candidates タブに保存可能な dict リスト

clip_candidate フォーマット（video_clip_candidates 保存用）:
  clip_id, account_id, reference_post_id, transcript_id,
  source_platform, source_video_url,
  start_time, end_time, duration_seconds,
  clip_title, hook, why_it_works,
  target_persona, x_post_angle, threads_post_angle,
  transcript_excerpt, clip_status,
  media_asset_id, storage_url,
  reuse_status, media_reuse_risk, imitation_risk,
  rights_status, permission_status,
  created_at, notes,
  confidence_score, cut_status, local_clip_path,
  clip_media_asset_id, text_generation_status,
  generated_draft_id, generated_at
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


# --------------------------------------------------------------------------- #
# プロンプト
# --------------------------------------------------------------------------- #

_SYSTEM_PROMPT = """あなたは動画コンテンツのクリップ分析専門家です。
文字起こしデータから、SNS投稿に転用できる有力なクリップ候補を抽出してください。

判断基準:
- 視聴者の感情・共感・驚きを引き出す場面
- 問題提起・核心的な主張・具体的なエピソードを含む場面
- 独立して意味が通じる（前後の文脈がなくても理解できる）場面
- 30秒〜2分程度に収まる場面（SNSで視聴完了されやすい長さ）

権利リスク評価:
- rights_status: "unknown"（デフォルト）/ "allowed" / "not_allowed"
- permission_status: "unknown"（デフォルト）/ "granted" / "denied" / "not_required"
- media_reuse_risk: "low" / "medium" / "high"
- imitation_risk: "low" / "medium" / "high"

必ずJSON配列で返してください。コメントや前置きは不要です。
"""

_USER_PROMPT_TEMPLATE = """以下の動画文字起こしから、SNSクリップ候補を{n_candidates}件抽出してください。

動画情報:
- account_id: {account_id}
- source_platform: {source_platform}
- source_video_url: {source_video_url}
- 動画全体の長さ: {total_duration_seconds}秒

文字起こしセグメント（JSON）:
{segments_json}

以下のJSONスキーマに従ってください（配列で返す）:
[
  {{
    "clip_title": "クリップのタイトル（30字以内）",
    "start_time": "HH:MM:SS形式（例: 00:01:30）",
    "end_time": "HH:MM:SS形式（例: 00:02:15）",
    "duration_seconds": 45,
    "hook": "SNS冒頭のフック文（視聴者が最初に見る1文、40字以内）",
    "why_it_works": "このクリップが有効な理由（50字以内）",
    "target_persona": "想定視聴者（20字以内）",
    "x_post_angle": "X投稿用の切り口・角度（50字以内）",
    "threads_post_angle": "Threads投稿用の切り口・角度（100字以内）",
    "transcript_excerpt": "対象区間の文字起こし抜粋（200字以内）",
    "confidence_score": 0.85,
    "media_reuse_risk": "low",
    "imitation_risk": "low",
    "rights_status": "unknown",
    "permission_status": "unknown",
    "notes": "特記事項があれば（なければ空文字）"
  }}
]
"""


# --------------------------------------------------------------------------- #
# モックレスポンス
# --------------------------------------------------------------------------- #

MOCK_CLIP_CANDIDATES = [
    {
        "clip_title": "夜職スカウトの実態を語る",
        "start_time": "00:01:15",
        "end_time": "00:02:30",
        "duration_seconds": 75,
        "hook": "スカウトマンが本音で語る「稼げる子と稼げない子の差」",
        "why_it_works": "具体的な差異を挙げており視聴者が自分事として捉えられる",
        "target_persona": "夜職を検討している20代女性",
        "x_post_angle": "スカウト目線の本音トーク",
        "threads_post_angle": "業界歴10年のスカウトマンが明かす、月収の差を生む意外な要因とは？",
        "transcript_excerpt": "稼げる子の共通点はね、素直さなんですよ。アドバイスを聞ける子は伸びる。",
        "confidence_score": 0.88,
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "",
    },
    {
        "clip_title": "初めてのお店選び完全ガイド",
        "start_time": "00:03:45",
        "end_time": "00:05:10",
        "duration_seconds": 85,
        "hook": "初めてのお店選び、99%の子が失敗する理由",
        "why_it_works": "失敗パターンの提示で共感と学習意欲を引き出す",
        "target_persona": "夜職未経験の20代前半",
        "x_post_angle": "失敗しないお店選び3つのポイント",
        "threads_post_angle": "お店選びで失敗する子に共通するパターンを3つ紹介します。知っておくだけで安心感が変わります。",
        "confidence_score": 0.82,
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "",
    },
    {
        "clip_title": "月収100万の現実",
        "start_time": "00:06:20",
        "end_time": "00:07:45",
        "duration_seconds": 85,
        "hook": "月収100万は本当に可能？現役スカウトが答える",
        "why_it_works": "数字と現実を示すことで信頼性が高まる",
        "target_persona": "高収入を目指す女性全般",
        "x_post_angle": "月収100万の現実を数字で解説",
        "threads_post_angle": "夢の月収100万円。実際に達成している子の特徴と、そこまでの道筋を具体的に話します。",
        "confidence_score": 0.79,
        "media_reuse_risk": "medium",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "金額言及あり。誇大表現に注意",
    },
    {
        "clip_title": "スカウトマンの選び方",
        "start_time": "00:08:30",
        "end_time": "00:09:50",
        "duration_seconds": 80,
        "hook": "「このスカウト、信用できる？」見分け方を教えます",
        "why_it_works": "安全性への不安を解消するコンテンツは拡散しやすい",
        "target_persona": "夜職検討中で安全性を重視する女性",
        "x_post_angle": "信頼できるスカウトの見分け方",
        "threads_post_angle": "スカウトマンを信頼できるかどうか、5つのポイントで確認できます。安全に働くために知っておいてほしい内容です。",
        "confidence_score": 0.91,
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "",
    },
    {
        "clip_title": "辞め時の判断基準",
        "start_time": "00:11:00",
        "end_time": "00:12:30",
        "duration_seconds": 90,
        "hook": "夜職を辞めるタイミング、プロはこう考える",
        "why_it_works": "出口戦略を語ることで信頼感と共感を同時に得られる",
        "target_persona": "現役夜職で辞め時を迷っている女性",
        "x_post_angle": "辞めどきを見極める3つのサイン",
        "threads_post_angle": "夜職はいつ辞めればいい？スカウト目線で「辞め時のサイン」を正直に話します。タイミングを間違えない方法。",
        "confidence_score": 0.85,
        "media_reuse_risk": "low",
        "imitation_risk": "low",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "",
    },
    {
        "clip_title": "業界の裏側トーク",
        "start_time": "00:14:15",
        "end_time": "00:15:45",
        "duration_seconds": 90,
        "hook": "業界10年でわかった、絶対に言えない裏話",
        "why_it_works": "秘密暴露系は好奇心を強く刺激する",
        "target_persona": "業界に興味がある幅広い年齢層",
        "x_post_angle": "業界の裏側を暴露",
        "threads_post_angle": "10年業界にいてはじめて語れる話。表には出てこない「実態」を今日だけ話します。",
        "confidence_score": 0.76,
        "media_reuse_risk": "high",
        "imitation_risk": "medium",
        "rights_status": "unknown",
        "permission_status": "unknown",
        "notes": "センシティブな内容が含まれる可能性。人間レビュー推奨",
    },
]


# --------------------------------------------------------------------------- #
# コア関数
# --------------------------------------------------------------------------- #

def analyze_transcript(
    transcript: dict[str, Any],
    account_id: str,
    *,
    n_candidates: int = 6,
    mock_llm: bool = True,
) -> list[dict[str, Any]]:
    """文字起こし1件からクリップ候補リストを生成する。

    Args:
        transcript: video_transcripts タブの1行 dict
        account_id: 対象アカウント
        n_candidates: 候補数（デフォルト6）
        mock_llm: True の場合は固定モックを返す（実API呼び出しなし）

    Returns:
        video_clip_candidates タブに保存可能な dict リスト
    """
    transcript_id = str(transcript.get("transcript_id", ""))
    reference_post_id = str(transcript.get("reference_post_id", ""))
    source_platform = str(transcript.get("source_platform", "youtube"))
    source_video_url = str(transcript.get("video_url", ""))
    total_duration = float(transcript.get("duration_seconds", 0) or 0)
    segments_json_str = str(transcript.get("segments_json", "[]"))

    if mock_llm:
        raw_candidates = _mock_candidates(n_candidates)
    else:
        raw_candidates = _call_gemini(
            account_id=account_id,
            source_platform=source_platform,
            source_video_url=source_video_url,
            total_duration_seconds=total_duration,
            segments_json_str=segments_json_str,
            n_candidates=n_candidates,
        )

    return [
        _normalize_candidate(
            raw=raw,
            account_id=account_id,
            transcript_id=transcript_id,
            reference_post_id=reference_post_id,
            source_platform=source_platform,
            source_video_url=source_video_url,
        )
        for raw in raw_candidates
    ]


def _mock_candidates(n: int) -> list[dict[str, Any]]:
    """モック候補を最大 n 件返す。"""
    return MOCK_CLIP_CANDIDATES[:n]


def _call_gemini(
    *,
    account_id: str,
    source_platform: str,
    source_video_url: str,
    total_duration_seconds: float,
    segments_json_str: str,
    n_candidates: int,
) -> list[dict[str, Any]]:
    """Gemini API を呼び出してクリップ候補を取得する。"""
    try:
        from llm_client import call_gemini_json
    except ImportError:
        return _mock_candidates(n_candidates)

    prompt = _USER_PROMPT_TEMPLATE.format(
        n_candidates=n_candidates,
        account_id=account_id,
        source_platform=source_platform,
        source_video_url=source_video_url,
        total_duration_seconds=int(total_duration_seconds),
        segments_json=segments_json_str[:3000],
    )

    result = call_gemini_json(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=prompt,
    )

    if isinstance(result, list):
        return result
    if isinstance(result, dict) and "candidates" in result:
        return result["candidates"]
    return _mock_candidates(n_candidates)


def _normalize_candidate(
    raw: dict[str, Any],
    *,
    account_id: str,
    transcript_id: str,
    reference_post_id: str,
    source_platform: str,
    source_video_url: str,
) -> dict[str, Any]:
    """Gemini 出力 / モックを video_clip_candidates 行に正規化する。"""
    clip_id = f"clip-{_short_uuid()}"
    start_time = str(raw.get("start_time", "00:00:00"))
    end_time = str(raw.get("end_time", "00:00:00"))
    duration_seconds = int(raw.get("duration_seconds", 0) or 0)
    confidence_score = float(raw.get("confidence_score", 0.0) or 0.0)
    rights_status = str(raw.get("rights_status", "unknown"))
    permission_status = str(raw.get("permission_status", "unknown"))
    media_reuse_risk = str(raw.get("media_reuse_risk", "low"))
    imitation_risk = str(raw.get("imitation_risk", "low"))

    return {
        "clip_id": clip_id,
        "account_id": account_id,
        "reference_post_id": reference_post_id,
        "transcript_id": transcript_id,
        "source_platform": source_platform,
        "source_video_url": source_video_url,
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": duration_seconds,
        "clip_title": str(raw.get("clip_title", ""))[:100],
        "hook": str(raw.get("hook", ""))[:200],
        "why_it_works": str(raw.get("why_it_works", ""))[:200],
        "target_persona": str(raw.get("target_persona", ""))[:100],
        "x_post_angle": str(raw.get("x_post_angle", ""))[:200],
        "threads_post_angle": str(raw.get("threads_post_angle", ""))[:400],
        "transcript_excerpt": str(raw.get("transcript_excerpt", ""))[:500],
        "clip_status": "candidate",
        "media_asset_id": "",
        "storage_url": "",
        "reuse_status": "pending",
        "media_reuse_risk": media_reuse_risk,
        "imitation_risk": imitation_risk,
        "rights_status": rights_status,
        "permission_status": permission_status,
        "created_at": _now(),
        "notes": str(raw.get("notes", "")),
        "confidence_score": str(confidence_score),
        "cut_status": "pending",
        "local_clip_path": "",
        "clip_media_asset_id": "",
        "text_generation_status": "pending",
        "generated_draft_id": "",
        "generated_at": "",
    }


# --------------------------------------------------------------------------- #
# バッチ処理
# --------------------------------------------------------------------------- #

def analyze_transcripts_batch(
    transcripts: list[dict[str, Any]],
    account_id: str,
    *,
    n_candidates: int = 6,
    mock_llm: bool = True,
) -> list[dict[str, Any]]:
    """複数の文字起こしを一括処理してクリップ候補リストを返す。"""
    all_candidates: list[dict[str, Any]] = []
    for tr in transcripts:
        candidates = analyze_transcript(
            tr,
            account_id,
            n_candidates=n_candidates,
            mock_llm=mock_llm,
        )
        all_candidates.extend(candidates)
        print(
            f"[clip-analyzer] transcript_id={tr.get('transcript_id', '?')!r} "
            f"→ {len(candidates)} 件の候補を抽出"
        )
    return all_candidates


def save_clip_candidates(
    client: Any,
    candidates: list[dict[str, Any]],
    *,
    dry_run: bool = True,
) -> dict[str, int]:
    """クリップ候補を video_clip_candidates タブに保存する。"""
    if dry_run:
        print(f"[dry-run] save_clip_candidates: {len(candidates)} 件（書き込みスキップ）")
        for c in candidates:
            print(
                f"  clip_id={c.get('clip_id', '?')!r} "
                f"title={str(c.get('clip_title', ''))[:30]!r} "
                f"confidence={c.get('confidence_score', '?')}"
            )
        return {"added": 0, "skipped": len(candidates), "errors": 0}

    added = skipped = errors = 0
    for c in candidates:
        try:
            result = client.save_video_clip_candidate(c)
            if result:
                added += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"[ERROR] save_video_clip_candidate 失敗: {e}")
            errors += 1
    return {"added": added, "skipped": skipped, "errors": errors}
