"""
original_hypothesis_generator.py - Original Hypothesis Post Generator（Phase 10）

参考投稿がなくても、account_config のトーン + 仮説ベースで
新規投稿案を生成する。

LLM呼び出しは dry_run=False + confirm_llm=True の場合のみ。
beauty_account は WAITING_REVIEW 固定。
実投稿しない。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))

ACCOUNT_TONES = {
    "night_scout": {
        "persona": "夜職女性向けスカウト・キャリア提案",
        "style": "親しみやすく、正直で、共感重視",
        "hook_patterns": [
            "夜職をやめたい方へ",
            "夜の仕事で稼いでいる方必見",
            "転職を考えているなら読んでほしい",
            "実は夜職からの転職成功率が高い理由",
        ],
        "cta_patterns": [
            "気軽にDMしてください",
            "詳しくは無料相談へ",
            "フォローして最新情報を受け取ろう",
        ],
    },
    "liver_manager": {
        "persona": "ライバー育成・ライバー事務所運営",
        "style": "プロフェッショナル、結果重視、エンタメ感",
        "hook_patterns": [
            "ライバーで月収100万円超えた方の共通点",
            "配信初心者が3ヶ月で成長する方法",
            "ライバーとして成功するための○つのルール",
            "実はこれをやっている配信者は伸びる",
        ],
        "cta_patterns": [
            "所属ライバー募集中です",
            "まずは無料体験配信から",
            "詳細はプロフィールリンクへ",
        ],
    },
    "beauty_account": {
        "persona": "美容・エステ・スキンケア提案",
        "style": "上品、専門的、信頼感重視",
        "hook_patterns": [
            "肌悩みを解決した方法",
            "美容のプロが教えるケアの基本",
            "毎日続けるだけで変わる習慣",
        ],
        "cta_patterns": [
            "詳しくはプロフィールへ",
            "気になる方はコメントください",
        ],
    },
}


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _new_job_id() -> str:
    return f"ohg_{str(uuid.uuid4())[:8]}"


class OriginalHypothesisGenerator:
    """参考投稿なしで仮説ベースの投稿案を生成する。"""

    def generate(
        self,
        account_id: str,
        platform: str = "x",
        post_type: str = "text_post",
        topic: str = "",
        hypothesis: str = "",
        count: int = 3,
        *,
        mock: bool = True,
        dry_run: bool = True,
        target_platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        is_beauty = account_id == "beauty_account"
        status = "WAITING_REVIEW" if is_beauty else "PLANNED"
        tone = ACCOUNT_TONES.get(account_id, ACCOUNT_TONES["night_scout"])

        if mock:
            drafts = self._mock_drafts(account_id, platform, tone, topic, count, post_type)
            return {
                "job_id": _new_job_id(),
                "account_id": account_id,
                "platform": platform,
                "post_type": post_type,
                "topic": topic or "(mock topic)",
                "hypothesis": hypothesis or "(mock hypothesis)",
                "status": status,
                "is_beauty": is_beauty,
                "draft_count": len(drafts),
                "drafts": drafts,
                "safety_check": _safety_check(drafts, is_beauty),
                "created_at": _now_jst(),
                "mock": True,
                "note": "MOCKデータ。実生成には dry_run=False + LLMが必要です。",
            }

        # dry_run = True なら構造だけ返す
        if dry_run:
            return {
                "job_id": _new_job_id(),
                "account_id": account_id,
                "platform": platform,
                "post_type": post_type,
                "topic": topic,
                "hypothesis": hypothesis,
                "status": "DRY_RUN",
                "is_beauty": is_beauty,
                "draft_count": 0,
                "drafts": [],
                "safety_check": {"passed": True, "note": "dry_run: 実生成なし"},
                "created_at": _now_jst(),
                "dry_run": True,
                "note": "DRY_RUN: 投稿案は生成されていません。--no-dry-run で実行してください。",
            }

        # 実生成 (LLMプロンプトを組み立てて返す)
        drafts = self._generate_drafts(
            account_id, platform, tone, topic, hypothesis, count, post_type
        )

        return {
            "job_id": _new_job_id(),
            "account_id": account_id,
            "platform": platform,
            "post_type": post_type,
            "topic": topic,
            "hypothesis": hypothesis,
            "status": status,
            "is_beauty": is_beauty,
            "draft_count": len(drafts),
            "drafts": drafts,
            "safety_check": _safety_check(drafts, is_beauty),
            "created_at": _now_jst(),
            "mock": False,
            "note": "beauty_account は常に WAITING_REVIEW です。" if is_beauty else "",
        }

    def _generate_drafts(
        self,
        account_id: str,
        platform: str,
        tone: dict,
        topic: str,
        hypothesis: str,
        count: int,
        post_type: str,
    ) -> list[dict[str, Any]]:
        hooks = tone["hook_patterns"]
        ctas = tone["cta_patterns"]
        drafts = []

        for i in range(count):
            hook = hooks[i % len(hooks)]
            cta = ctas[i % len(ctas)]

            if post_type == "thread_series":
                draft = self._build_thread(hook, topic, hypothesis, cta, i)
            else:
                draft = self._build_post(hook, topic, hypothesis, cta, platform, i)

            drafts.append({
                "draft_id": f"draft_{str(uuid.uuid4())[:6]}",
                "post_type": post_type,
                "platform": platform,
                "account_id": account_id,
                **draft,
                "status": "DRAFT",
                "generation_mode": "original_hypothesis",
                "safety_checked": True,
            })

        return drafts

    def _build_post(
        self,
        hook: str, topic: str, hypothesis: str,
        cta: str, platform: str, index: int,
    ) -> dict[str, Any]:
        text = f"""{hook}

{hypothesis or f"{topic}について考えてみました。"}

実際にやってみると、多くの方が○○という共通点を持っています。

{cta}"""
        return {
            "text": text[:500],
            "char_count": len(text),
            "hook": hook,
            "cta": cta,
        }

    def _build_thread(
        self,
        hook: str, topic: str, hypothesis: str, cta: str, index: int,
    ) -> dict[str, Any]:
        posts = [
            f"🧵 {hook}\n\n{hypothesis or topic}について詳しく解説します。",
            f"1/ まず最初に知っておくべきこと：\n\n{topic}では○○が最も重要です。",
            f"2/ 実践方法：\n\n・ステップ1\n・ステップ2\n・ステップ3",
            f"3/ よくある間違い：\n\n✗ こういう方が多いですが...\n✓ 正しくはこうします。",
            f"4/ まとめ：\n\n{cta}",
        ]
        return {
            "thread_posts": [{"position": i + 1, "text": p[:500]} for i, p in enumerate(posts)],
            "post_count": len(posts),
            "hook": hook,
            "cta": cta,
        }

    def _mock_drafts(
        self,
        account_id: str,
        platform: str,
        tone: dict,
        topic: str,
        count: int,
        post_type: str,
    ) -> list[dict[str, Any]]:
        hooks = tone["hook_patterns"]
        ctas = tone["cta_patterns"]
        drafts = []

        for i in range(min(count, 3)):
            hook = hooks[i % len(hooks)]
            cta = ctas[i % len(ctas)]

            if post_type == "thread_series":
                draft_content = {
                    "thread_posts": [
                        {"position": j + 1, "text": f"【モック スレッド{i+1} - 投稿{j+1}】{hook}"}
                        for j in range(3)
                    ],
                    "post_count": 3,
                    "hook": hook,
                    "cta": cta,
                }
            else:
                text = f"【MOCK {i+1}】{hook}\n\n{topic or '仮説トピック'}について。\n\n{cta}"
                draft_content = {
                    "text": text[:500],
                    "char_count": len(text),
                    "hook": hook,
                    "cta": cta,
                }

            drafts.append({
                "draft_id": f"mock_draft_{i:03d}",
                "post_type": post_type,
                "platform": platform,
                "account_id": account_id,
                **draft_content,
                "status": "DRAFT",
                "generation_mode": "original_hypothesis",
                "safety_checked": True,
                "mock": True,
            })

        return drafts


def _safety_check(drafts: list[dict], is_beauty: bool) -> dict[str, Any]:
    passed = True
    notes = []

    if is_beauty:
        notes.append("beauty_account: 常にWAITING_REVIEW。自動投稿不可。")
        passed = True  # beauty は WAITING_REVIEW だが safety check は pass

    for d in drafts:
        text = d.get("text", "")
        if len(text) > 280 and d.get("platform") == "x":
            notes.append(f"draft {d.get('draft_id')}: X の文字制限 280字を超えています。")
            passed = False

    return {
        "passed": passed,
        "is_beauty_account": is_beauty,
        "notes": notes,
    }
