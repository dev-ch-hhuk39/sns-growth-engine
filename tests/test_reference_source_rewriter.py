from __future__ import annotations

import json

import pytest

from src.generation import reference_source_rewriter as rewriter
from src.generation.reference_source_rewriter import ReferenceRewriteError
from src.generation.video_reference_generator import VideoReferenceGenerator
from src.video.video_understanding import VideoUnderstanding


def test_threads_uses_actual_post_text():
    material = rewriter.build_source_material({
        "source_platform": "threads",
        "text": "体験入店で見るべきポイントは客層とスタッフ対応。",
        "title": "ignored title",
    })
    assert "体験入店で見るべきポイントは客層とスタッフ対応。" in material
    assert "[post_text_or_caption]" in material


def test_video_without_transcript_fails_closed():
    with pytest.raises(ReferenceRewriteError, match="requires transcript"):
        rewriter.build_source_material({
            "source_platform": "youtube",
            "title": "動画タイトル",
            "description": "スポンサー情報と概要欄だけ",
            "text": "短い説明",
        })


def test_video_transcript_is_primary_and_description_is_supplementary():
    material = rewriter.build_source_material({
        "source_platform": "youtube",
        "title": "動画タイトル",
        "text": "動画キャプション",
        "transcript": "本編では接客で大切な聞き方について話している。",
        "description": "スポンサー情報",
    })
    assert "[transcript]" in material
    assert "本編では接客で大切な聞き方" in material
    assert "[supplementary_description]" in material


def test_prompt_contains_source_and_no_canned_topic_injection():
    source = "[post_text_or_caption]\n売上が落ちた時はお客様への連絡頻度を見直す。"
    prompt = rewriter.build_reference_rewrite_prompt(
        account_id="night_scout",
        source_material=source,
    )
    assert source in prompt
    assert "SOURCEの中心テーマ" in prompt
    assert "時給と控除を含めた条件を比べて手取りを確認する" not in prompt


def test_liver_prompt_requires_source_grounded_concrete_action_or_skip():
    source = "[transcript]\n初見が入りやすい配信導線を説明している。"
    prompt = rewriter.build_reference_rewrite_prompt(
        account_id="liver_manager",
        source_material=source,
    )
    assert source in prompt
    assert "具体的な行動を最低1つ" in prompt
    assert "なぜ有効かの理由や因果を1文" in prompt
    assert "一般論で補わず __SKIP_SOURCE__" in prompt


def test_rewrite_uses_generation_and_semantic_fidelity(monkeypatch):
    responses = iter([
        "売上が落ちた時こそ、連絡数を増やすより相手ごとの距離感を見直したい。\n\n僕なら、返信の温度感を見ながら連絡頻度を整える。",
        json.dumps({"pass": True, "reason": "中心テーマが一致"}, ensure_ascii=False),
    ])
    monkeypatch.setattr(rewriter, "_call_gemini", lambda *args, **kwargs: next(responses))
    result = rewriter.rewrite_reference_post(
        account_id="night_scout",
        source={"source_platform": "threads", "text": "売上が落ちた時はお客様への連絡頻度を見直す。"},
    )
    assert result["semantic_fidelity"]["pass"] is True
    assert result["generation_strategy"] == "source_grounded_gemini_v1"
    assert result["feature_schema_version"] == "post_features_v1"


def test_semantic_mismatch_is_blocked(monkeypatch):
    responses = iter([
        "時給と控除を確認して手取りを計算しよう。これは別テーマの文章です。十分な長さもあります。",
        json.dumps({"pass": False, "reason": "SOURCEと別テーマ"}, ensure_ascii=False),
    ])
    monkeypatch.setattr(rewriter, "_call_gemini", lambda *args, **kwargs: next(responses))
    with pytest.raises(ReferenceRewriteError, match="semantic fidelity blocked"):
        rewriter.rewrite_reference_post(
            account_id="night_scout",
            source={"source_platform": "threads", "text": "接客中の会話で相手の話を最後まで聞くことが大切。"},
        )


def test_understanding_text_platform_preserves_source_text():
    result = VideoUnderstanding().analyze(
        {
            "source_platform": "threads",
            "text": "初見さんには最初の質問を一つに絞る。",
            "title": "",
            "description": "",
            "source_id": "src1",
            "post_url": "https://www.threads.net/example",
        },
        account_id="liver_manager",
        target_platform="threads",
        mock=False,
    )
    assert result["semantic_ready"] is True
    assert result["source_text"] == "初見さんには最初の質問を一つに絞る。"


def test_understanding_tiktok_without_transcript_is_not_ready():
    result = VideoUnderstanding().analyze(
        {
            "source_platform": "tiktok",
            "text": "キャプションだけ",
            "title": "TikTok動画",
            "source_id": "src2",
        },
        account_id="liver_manager",
        target_platform="threads",
        mock=False,
    )
    assert result["semantic_ready"] is False
    assert result["semantic_block_reason"] == "video_transcript_required"


def test_video_reference_generator_uses_shared_rewriter(monkeypatch):
    from src.generation import video_reference_generator as module

    monkeypatch.setattr(
        module,
        "rewrite_reference_post",
        lambda **kwargs: {
            "public_post_text": "初見さんが入りやすい配信は、最初の質問を一つに絞る。\n\n答えやすい入口を作ると会話が始まりやすいです。",
            "generation_model": "test-model",
            "generation_strategy": "source_grounded_gemini_v1",
            "semantic_fidelity": {"pass": True, "reason": "test"},
        },
    )
    result = VideoReferenceGenerator().generate(
        {
            "source_id": "src3",
            "post_url": "https://www.threads.net/example",
            "platform": "threads",
            "source_text": "初見さんには最初の質問を一つに絞る。",
            "semantic_ready": True,
            "has_transcript": False,
            "clip_candidates": [],
        },
        account_id="liver_manager",
        target_platform="threads",
        generation_mode="reference_based_text",
        mock=False,
    )
    assert result["draft_count"] == 1
    assert result["drafts"][0]["generation_strategy"] == "source_grounded_gemini_v1"
