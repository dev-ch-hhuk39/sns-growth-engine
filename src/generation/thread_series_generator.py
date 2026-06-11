"""
thread_series_generator.py - ツリー投稿（thread_series）生成（Phase 6.2）

account_config 駆動でアカウント別にスレッドシリーズを生成する。
root_hook から始まる reply ツリーを生成し、全投稿は WAITING_REVIEW 状態で出力する。

安全ガード:
  - draft_only アカウントは WAITING_REVIEW のみ。READY / POSTED への遷移禁止。
  - MOCK_LLM=true または DRY_RUN=true の場合、実APIを呼び出さない。
  - 実SNS投稿は行わない。
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _V2_ROOT + "/src")

from llm_client import call_gemini_json
from seeds import ACCOUNT_FORBIDDEN_KEYWORDS, ACCOUNT_FORBIDDEN_THEMES

JST = timezone(timedelta(hours=9))

THREAD_POST_ROLES = [
    "hook",
    "context",
    "reason",
    "example",
    "checklist",
    "objection_handling",
    "proof",
    "cta",
]

_MOCK_RESPONSES: dict[str, dict[str, Any]] = {
    "night_scout": {
        "series_theme": "夜職で月50万稼ぐための3ステップ",
        "target_audience": "キャバ嬢・夜職女性",
        "risk_level": "low",
        "rights_review_required": False,
        "posts": [
            {"role": "hook", "text": "夜職で月50万稼ぐ女性と月15万止まりの女性の差、知ってる？"},
            {"role": "context", "text": "俺が10年スカウトをやってきて見た共通点がある。\n月収に差がつく理由は「努力の量」じゃない。"},
            {"role": "reason", "text": "差がつく本当の理由は「仕組みを作れているか」どうかだ。\n指名を増やす動きと、常連を作る動きは全然違う。"},
            {"role": "example", "text": "月50万稼いでる子は必ずSNSを使っている。\n投稿→共感→LINE→相談→来店、この流れができている。"},
            {"role": "cta", "text": "今の自分の状況を聞かせて。\n相談はLINEで↓"},
        ],
    },
    "liver_manager": {
        "series_theme": "TikTokライブ初月から稼ぐための3つの習慣",
        "target_audience": "TikTokライブ未経験者・既存ライバー",
        "risk_level": "low",
        "rights_review_required": False,
        "posts": [
            {"role": "hook", "text": "TikTokライブ初月から稼げる人と稼げない人、差は意外なところにある。"},
            {"role": "context", "text": "私がマネージャーとして育成してきた中で気づいたこと。\n最初の3ヶ月が全てを決める。"},
            {"role": "reason", "text": "稼げるライバーは「配信の質」より「配信の習慣」を先に作る。\n毎日30分でも継続できる人が最終的に伸びる。"},
            {"role": "example", "text": "ある子は最初1ダイヤも入らなかった。\n毎日配信を3週間続けた結果、月5万達成。今は月30万超。"},
            {"role": "cta", "text": "あなたの配信状況を聞かせてください。\n相談はLINEで↓"},
        ],
    },
    "beauty_account": {
        "series_theme": "毎日のスキンケアで差がつく3つのポイント",
        "target_audience": "美容に興味のある女性・スキンケアに悩む20〜40代",
        "risk_level": "low",
        "rights_review_required": False,
        "posts": [
            {"role": "hook", "text": "スキンケアを頑張っているのに肌が変わらない理由、知ってる？"},
            {"role": "context", "text": "美容の知識がある人でも意外と見落としているポイントがある。\n順番と選び方が全てを決める。"},
            {"role": "reason", "text": "化粧水をたっぷりつけるより、洗顔後の5分が大事。\n肌の吸収タイミングを逃すと効果が半減する。"},
            {"role": "example", "text": "私のお客様の多くが「洗顔をやめた」だけで肌トラブルが改善した。\n正しい順番に変えるだけで肌の反応が変わる。"},
            {"role": "cta", "text": "肌の悩みを教えてください。\n美容相談はLINEで↓"},
        ],
    },
}

_DEFAULT_MOCK = {
    "series_theme": "サンプルシリーズテーマ",
    "target_audience": "一般ターゲット",
    "risk_level": "low",
    "rights_review_required": False,
    "posts": [
        {"role": "hook", "text": "[MOCK] フックポスト。読者の興味を引く1行。"},
        {"role": "context", "text": "[MOCK] コンテキスト。なぜこれが重要なのかを説明。"},
        {"role": "reason", "text": "[MOCK] 理由。具体的な根拠を提示。"},
        {"role": "cta", "text": "[MOCK] CTA。行動を促すメッセージ。\n相談はLINEで↓"},
    ],
}


@dataclass
class ThreadPost:
    post_index: int
    post_role: str
    text: str
    char_count: int
    status: str = "WAITING_REVIEW"
    safety_flags: str = ""
    platform: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ThreadSeries:
    series_id: str
    account_id: str
    platform: str
    generation_mode: str
    status: str
    root_hook: str
    series_theme: str
    target_audience: str
    post_count: int
    posts: list[ThreadPost]
    created_at: str
    risk_level: str
    rights_review_required: bool
    mock: bool
    generation_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["posts"] = [p.to_dict() for p in self.posts]
        return d


class ThreadSeriesGenerator:
    """アカウント設定駆動のスレッドシリーズ生成クラス。"""

    def __init__(self) -> None:
        pass

    def _get_forbidden_block(self, account_id: str) -> str:
        kw = ACCOUNT_FORBIDDEN_KEYWORDS.get(account_id, [])
        th = ACCOUNT_FORBIDDEN_THEMES.get(account_id, [])
        lines = []
        if kw:
            lines.append("禁止キーワード: " + "、".join(kw))
        if th:
            lines.append("禁止テーマ: " + "、".join(th))
        return "\n".join(lines)

    def _build_prompt(
        self,
        account_id: str,
        platform: str,
        theme: str,
        post_count: int,
        persona: str,
        target_audience: str,
        tone: str,
        char_limit: int,
    ) -> str:
        forbidden = self._get_forbidden_block(account_id)
        roles_desc = "\n".join(
            f"  - {r}" for r in THREAD_POST_ROLES[:post_count]
        )
        return f"""あなたはSNSコンテンツライターです。
以下のアカウント設定に従い、ツリー投稿（thread_series）を生成してください。

## アカウント情報
- account_id: {account_id}
- ペルソナ: {persona}
- ターゲット読者: {target_audience}
- トーン: {tone}
- プラットフォーム: {platform}
- 1投稿あたりの文字数上限: {char_limit}文字

## テーマ
{theme}

## 投稿数
{post_count}投稿（以下のroleに対応させること）
{roles_desc}

## 禁止事項
{forbidden if forbidden else "特になし"}

## 出力形式（JSONのみ）
{{
  "series_theme": "シリーズのまとめテーマ",
  "target_audience": "想定読者",
  "risk_level": "low / medium / high",
  "rights_review_required": false,
  "posts": [
    {{"role": "hook", "text": "最初の1投稿目"}},
    {{"role": "context", "text": "2投稿目"}},
    ...
  ]
}}"""

    def generate(
        self,
        account_id: str,
        platform: str,
        theme: str,
        post_count: int = 4,
        persona: str = "",
        target_audience: str = "",
        tone: str = "",
        char_limit: int = 120,
        mock_llm: bool = False,
    ) -> ThreadSeries:
        """スレッドシリーズを生成して返す。実投稿は行わない。"""
        try:
            from accounts.account_config import load_account_config
            cfg = load_account_config(account_id)
            if not persona:
                persona = cfg.persona
            if not target_audience:
                target_audience = cfg.target_audience
            if not tone:
                tone = cfg.tone
            limits = cfg.get_char_limits(platform)
            char_limit = limits["soft"]
            draft_only = cfg.is_draft_only()
        except FileNotFoundError:
            draft_only = False

        series_id = f"ts_{account_id}_{platform}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(JST).isoformat()

        mock_key = account_id if account_id in _MOCK_RESPONSES else None
        mock_data = _MOCK_RESPONSES.get(mock_key, _DEFAULT_MOCK) if mock_key else _DEFAULT_MOCK

        if mock_llm:
            os.environ["MOCK_LLM"] = "true"

        prompt = self._build_prompt(
            account_id=account_id,
            platform=platform,
            theme=theme,
            post_count=post_count,
            persona=persona,
            target_audience=target_audience,
            tone=tone,
            char_limit=char_limit,
        )

        # アカウント固有のモックデータを動的に生成（post_count に合わせる）
        mock_posts = (mock_data.get("posts") or [])[:post_count]
        if len(mock_posts) < post_count:
            for i in range(len(mock_posts), post_count):
                role = THREAD_POST_ROLES[i] if i < len(THREAD_POST_ROLES) else "context"
                mock_posts.append({"role": role, "text": f"[MOCK] {role}投稿"})

        dry_run_mock = {
            "series_theme": theme or mock_data.get("series_theme", ""),
            "target_audience": target_audience or mock_data.get("target_audience", ""),
            "risk_level": "low",
            "rights_review_required": False,
            "posts": mock_posts,
        }

        result = call_gemini_json(prompt, dry_run_mock=dry_run_mock)
        is_mock = mock_llm or (result == dry_run_mock)

        raw_posts = result.get("posts", [])
        posts: list[ThreadPost] = []
        for i, p in enumerate(raw_posts[:post_count]):
            text = p.get("text", "")
            role = p.get("role", THREAD_POST_ROLES[i] if i < len(THREAD_POST_ROLES) else "context")
            posts.append(ThreadPost(
                post_index=i,
                post_role=role,
                text=text,
                char_count=len(text),
                status="WAITING_REVIEW",
                platform=platform,
            ))

        root_hook = posts[0].text if posts else ""

        # draft_only 強制チェック: READY 遷移不可
        series_status = "WAITING_REVIEW"
        if draft_only:
            generation_notes = f"draft_only アカウント: {account_id}。READY化・投稿禁止。"
        else:
            generation_notes = result.get("generation_notes", "")

        return ThreadSeries(
            series_id=series_id,
            account_id=account_id,
            platform=platform,
            generation_mode="mock" if is_mock else "llm",
            status=series_status,
            root_hook=root_hook,
            series_theme=result.get("series_theme", theme),
            target_audience=result.get("target_audience", target_audience),
            post_count=len(posts),
            posts=posts,
            created_at=now,
            risk_level=result.get("risk_level", "low"),
            rights_review_required=result.get("rights_review_required", False),
            mock=is_mock,
            generation_notes=generation_notes,
        )
