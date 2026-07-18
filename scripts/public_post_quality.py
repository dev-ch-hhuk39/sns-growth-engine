#!/usr/bin/env python3
"""Public post generation and final validation gates.

Only ``public_post_text`` may ever be handed to a publisher. Internal
analysis, reference metadata, and scoring notes must stay out of public text.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_FILE = ROOT / "config/post_generation_rules.json"

INTERNAL_LEAK_TERMS = [
    "今回の切り口",
    "threads /",
    "night_work_scout",
    "night_scout",
    "liver_manager",
    "target_account_id",
    "source",
    "reference",
    "参照元",
    "source_url",
    "source_id",
    "queue_id",
    "result_id",
    "category",
    "usage_scope",
    "trend_signal",
    "clip_candidate",
    "投稿案",
    "生成",
    "分解して使う",
    "そのまま真似るのではなく",
    "構成・フック",
    "投稿アイデア",
    "LINE/DMへの導線は最後",
    "導線は最後",
    "AI",
    "内部",
    "metadata",
    "transcript",
    "youtube_video_id_missing",
    "PLAN_ONLY",
    "AUTO_READY",
    "WAITING_REVIEW",
    "dry-run",
    "apply",
    "score",
    "safety_score",
    "risk_score",
]

SOURCE_METADATA_PATTERNS = [
    r"\bthreads\s*/",
    r"\bx\.com/",
    r"\byoutube\.com/",
    r"\btiktok\.com/",
    r"\bhttps?://",
    r"\bsource[_-]?\w*",
    r"\bqueue[_-]?\w*",
    r"\bresult[_-]?\w*",
]

AGGRESSIVE_OR_RISKY_TERMS = [
    "絶対稼げる",
    "必ず稼げる",
    "100%稼げる",
    "確実に稼げる",
    "誰でも月収",
    "楽して稼げる",
    "保証します",
    "今すぐ応募",
    "即日で稼げる",
    "ノーリスク",
]

ACCOUNT_TERMS = {
    "night_scout": ("夜職", "キャバ", "店", "働く", "時給", "ノルマ", "担当", "相談", "出勤", "移籍"),
    "liver_manager": ("配信", "ライバー", "TikTok LIVE", "LIVE", "リスナー", "初見", "コメント", "事務所", "ギフト"),
}


def load_post_generation_rules(path: Path = RULES_FILE) -> dict[str, Any]:
    if not path.exists():
        return {"quality_thresholds": {}, "accounts": {}, "account_rotation": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def extract_public_post_text(value: Any) -> str:
    """Return public text only, even when passed structured generation output."""
    if isinstance(value, dict):
        return str(value.get("public_post_text", "")).strip()
    raw = str(value or "").strip()
    if raw.startswith("{") and "public_post_text" in raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return str(parsed.get("public_post_text", "")).strip()
        except json.JSONDecodeError:
            return ""
    return raw


def build_generation_output(
    *,
    internal_analysis: str,
    public_post_text: str,
    safety_notes: str = "",
    blocked_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "internal_analysis": internal_analysis,
        "public_post_text": public_post_text,
        "safety_notes": safety_notes,
        "blocked_reasons": list(blocked_reasons or []),
    }


def _contains_terms(text: str, terms: list[str]) -> list[str]:
    low = text.lower()
    return [term for term in terms if term and term.lower() in low]


def _risk_score(text: str) -> int:
    score = 0
    if _contains_terms(text, AGGRESSIVE_OR_RISKY_TERMS):
        score += 30
    if any(k in text for k in ("絶対", "必ず", "保証", "誰でも", "簡単に稼げる")):
        score += 15
    if any(k in text for k in ("晒す", "叩く", "詐欺", "未成年", "薬")):
        score += 30
    return min(100, score)


def _cta_pressure_score(text: str) -> int:
    score = 0
    if any(k in text for k in ("今すぐ", "絶対", "必ず", "急いで", "限定")):
        score += 25
    if text.count("DM") + text.count("LINE") >= 2:
        score += 20
    if any(k in text for k in ("応募", "登録", "申し込み")):
        score += 15
    return min(100, score)


def _naturalness_score(text: str) -> int:
    if not text.strip():
        return 0
    score = 86
    if "。" not in text:
        score -= 15
    if len(text) < 80 or len(text) > 520:
        score -= 18
    if len(text.splitlines()) > 16:
        score -= 10
    if re.search(r"[A-Za-z_]{12,}", text):
        score -= 25
    if _contains_terms(text, INTERNAL_LEAK_TERMS):
        score -= 50
    return max(0, min(100, score))


def _reader_value_score(text: str, account_id: str) -> int:
    value_terms = ("理由", "大事", "まず", "見る", "整理", "変わる", "選ぶ", "続かない", "入りやすい", "具体")
    score = 72 + min(18, sum(1 for term in value_terms if term in text) * 4)
    if len(text) < 80:
        score -= 20
    if account_id == "night_scout" and any(k in text for k in ("店", "時給", "ノルマ", "担当", "出勤", "相談")):
        score += 8
    if account_id == "liver_manager" and any(k in text for k in ("初見", "コメント", "配信", "リスナー", "空気")):
        score += 8
    return max(0, min(100, score))


def _account_fit_score(text: str, account_id: str) -> int:
    terms = ACCOUNT_TERMS.get(account_id, ())
    hits = sum(1 for term in terms if term in text)
    score = 68 + min(24, hits * 6)
    if account_id == "beauty_account":
        score = 0
    return max(0, min(100, score))


def final_public_post_validator(text: Any, account_id: str = "") -> dict[str, Any]:
    public_text = extract_public_post_text(text)
    reasons: list[str] = []
    internal_hits = _contains_terms(public_text, INTERNAL_LEAK_TERMS)
    metadata_hits = [p for p in SOURCE_METADATA_PATTERNS if re.search(p, public_text, re.IGNORECASE)]
    hashtag_count = len(re.findall(r"(?:^|\s)#\S+", public_text))
    risk = _risk_score(public_text)
    cta = _cta_pressure_score(public_text)
    natural = _naturalness_score(public_text)
    reader = _reader_value_score(public_text, account_id)
    fit = _account_fit_score(public_text, account_id)
    quality = min(100, int((natural + reader + fit + max(0, 100 - cta) + max(0, 100 - risk)) / 5))

    if internal_hits:
        reasons.append("internal_terms")
    if metadata_hits:
        reasons.append("source_metadata_or_url")
    if "これは投稿案" in public_text or "投稿案です" in public_text:
        reasons.append("draft_label")
    if hashtag_count > 4:
        reasons.append("too_many_hashtags")
    if risk > 10:
        reasons.append("risk_score_above_max")
    if cta > 30:
        reasons.append("cta_pressure_above_max")
    if len(public_text) < 80:
        reasons.append("too_short")
    if len(public_text) > 520:
        reasons.append("too_long")
    if natural < 80:
        reasons.append("naturalness_below_threshold")
    if reader < 80:
        reasons.append("reader_value_below_threshold")
    if fit < 80:
        reasons.append("account_fit_below_threshold")
    if quality < 85:
        reasons.append("quality_below_threshold")

    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "public_post_text": public_text,
        "text_length": len(public_text),
        "internal_leak_check": {
            "status": "PASS" if not internal_hits else "BLOCKED",
            "hits": internal_hits,
            "internal_leak_score": len(internal_hits),
        },
        "source_metadata_check": {
            "status": "PASS" if not metadata_hits else "BLOCKED",
            "hits": metadata_hits,
        },
        "account_fit_check": {
            "status": "PASS" if fit >= 80 else "BLOCKED",
            "account_fit_score": fit,
        },
        "public_post_quality_score": quality,
        "reader_value_score": reader,
        "naturalness_score": natural,
        "account_fit_score": fit,
        "cta_pressure_score": cta,
        "risk_score": risk,
        "similarity_to_source": 0.0,
    }


def generate_reader_facing_post(account_id: str, index: int = 1) -> dict[str, Any]:
    """Deterministic account-specific public text for autonomous text-only posts."""
    if account_id == "liver_manager":
        variants = [
            (
                "配信で伸びない人ほど、最初から面白いことを言おうとしすぎる。\n\n"
                "でも初心者の配信で大事なのは、面白さより入りやすさ。\n\n"
                "入った瞬間に何を話していいかわからない。\n"
                "コメントしても拾われるかわからない。\n"
                "常連だけで盛り上がっていて入りづらい。\n\n"
                "この状態だと、初見はすぐ抜ける。\n\n"
                "まずは、来てくれてありがとう、今この話をしてるよ、気軽にコメントしてねを自然に言えること。\n\n"
                "配信は才能より、入りやすい空気を作れるかが大きい。"
            ),
            (
                "ライバーを始めたいのに動けない人は、配信内容より先に不安を整理した方がいい。\n\n"
                "何を話すか。\n"
                "誰も来なかったらどうするか。\n"
                "コメントが止まったらどうするか。\n"
                "生活リズムに無理がないか。\n\n"
                "ここが曖昧なまま始めると、数回でしんどくなる。\n\n"
                "最初から完璧に話す必要はない。\n"
                "続けられる時間と、初見が入りやすい一言を決めるだけでもかなり変わる。"
            ),
            (
                "配信でコメントが増えない時、話す内容だけを変えても伸びないことがある。\n\n"
                "初見が入りづらい空気だと、どれだけ頑張って話していてもすぐ抜けられる。\n\n"
                "まず見るのは、入室した人に気づけているか。\n"
                "今何の話をしているか伝えているか。\n"
                "コメントしていい雰囲気を作れているか。\n\n"
                "配信は一方的に話す場じゃなくて、入りやすい会話の入口を作る場。\n"
                "ここを整えるだけで、初見の残り方は変わる。"
            ),
            (
                "ライバー事務所を選ぶ時、条件だけで決めるとあとで迷いやすい。\n\n"
                "大事なのは、配信を続けるための相談ができるか。\n"
                "数字が落ちた時に一緒に原因を見てくれるか。\n"
                "自分の生活リズムに合った配信設計を考えてくれるか。\n\n"
                "最初から全部わかっている人はいない。\n"
                "だからこそ、始める前にサポートの中身を確認した方がいい。"
            ),
            (
                "配信を始めたばかりの人ほど、毎回違うことをしようとして疲れやすい。\n\n"
                "でも最初に必要なのは、派手な企画より続けられる型。\n\n"
                "始まりの挨拶。\n"
                "今日話すテーマ。\n"
                "初見への一言。\n"
                "コメントが止まった時の話題。\n\n"
                "この流れがあるだけで、配信中に迷う時間が減る。\n"
                "慣れるまでは才能より、続けやすい型を持つ方が強い。"
            ),
            (
                "配信がしんどくなる人は、数字だけを見すぎていることが多い。\n\n"
                "もちろん結果は大事。\n"
                "でも毎回の視聴者数だけで良し悪しを決めると、続ける気力が削られる。\n\n"
                "今日は初見に挨拶できたか。\n"
                "コメントを拾えたか。\n"
                "次も来やすい空気を作れたか。\n\n"
                "小さい改善を見られる人ほど、配信は続きやすい。"
            ),
            (
                "TikTok LIVEに興味があるなら、最初から完璧なキャラを作らなくていい。\n\n"
                "むしろ無理に盛りすぎると、続けるのがきつくなる。\n\n"
                "話しやすい時間帯。\n"
                "自然に話せるテーマ。\n"
                "初見に返しやすい一言。\n"
                "疲れすぎない配信時間。\n\n"
                "まずはこのあたりを決めるだけで十分。\n"
                "配信は始め方より、続けられる形を作れるかが大事。"
            ),
            (
                "リスナーが定着しない時は、話の面白さより安心感を見直した方がいい。\n\n"
                "コメントしても反応が薄い。\n"
                "内輪だけで盛り上がっている。\n"
                "何を話している配信かわかりにくい。\n\n"
                "この状態だと、初見は残りづらい。\n\n"
                "まずは来てくれた人が入れる余白を作ること。\n"
                "配信は盛り上げる前に、参加しやすくするのが大事。"
            ),
            (
                "配信を伸ばしたいなら、長く話すより反応しやすい話題を置いた方がいい。\n\n"
                "最近ハマっていること。\n"
                "今日あった小さい出来事。\n"
                "二択で答えられる質問。\n"
                "初見でも入れる軽いテーマ。\n\n"
                "コメントは、書きやすい入口があるだけで増えやすい。\n"
                "難しい話をするより、参加しやすい空気を作る方が先。"
            ),
            (
                "配信初心者が最初につまずくのは、話題がないことより一人で抱えすぎること。\n\n"
                "伸びない理由がわからない。\n"
                "どの時間に配信すればいいかわからない。\n"
                "コメントが少ないと不安になる。\n\n"
                "ここを一人で判断し続けると、だんだんしんどくなる。\n\n"
                "最初は配信内容より、振り返り方を作ること。\n"
                "続けられる人は、毎回少しずつ直す場所を見つけている。"
            ),
            (
                "ライバーが配信時間を決める時、空いている時間だけで選ぶと続きにくい。\n\n"
                "眠い時間に無理をする。\n"
                "準備する余裕がない。\n"
                "終わったあとに生活が崩れる。\n"
                "次の日まで疲れが残る。\n\n"
                "続けるには、配信する時間だけじゃなく前後の余白も大事。\n"
                "リスナーに会いやすく、自分も無理なく続けられる時間帯を先に決めた方が安定しやすい。"
            ),
            (
                "ギフトを増やしたい時ほど、お願いの強さより応援したくなる流れを見た方がいい。\n\n"
                "初見が入りやすい。\n"
                "コメントを拾ってもらえる。\n"
                "話していて居場所がある。\n"
                "また来たい理由がある。\n\n"
                "この土台がないままお願いだけ強くすると、見ている側は疲れる。\n"
                "配信は先に関係性を作る方が伸びやすい。"
            ),
            (
                "配信の終わり方が曖昧だと、次も見に来る理由が残りにくい。\n\n"
                "今日来てくれたことへのお礼。\n次に話す予定。\nまたコメントしやすい一言。\n\n"
                "この三つがあるだけで、初見にも常連にも次の入口ができる。\n"
                "最後の数分まで、参加しやすい空気を作ることが大事。"
            ),
            (
                "配信で話題が途切れた時、焦ってずっと話し続けなくていい。\n\n"
                "最近食べたもの。\n今日いちばん困ったこと。\n今週やってみたいこと。\n\n"
                "答えやすい話題を一つ置くと、コメントは入りやすくなる。\n"
                "沈黙を怖がるより、会話の入口を準備しておく方が続けやすい。"
            ),
            (
                "配信を続けるなら、毎回反省を増やしすぎない方がいい。\n\n"
                "初見に挨拶できたか。\nコメントを一つ丁寧に拾えたか。\n次回の話題を一つ決められたか。\n\n"
                "見る場所を絞ると、改善は続けやすい。\n"
                "小さな変化を積み重ねる方が、気持ちも配信も安定しやすい。"
            ),
            (
                "配信前の準備は、機材を増やすことより気持ちに余白を作ること。\n\n"
                "話すテーマを一つ。\n初見への挨拶を一つ。\nコメントが止まった時の質問を一つ。\n\n"
                "これだけ決めておけば、始まってから慌てにくい。\n"
                "続く配信は、準備が完璧だからではなく無理が少ないから続く。"
            ),
            (
                "初見が来た時、すぐに盛り上げようとしなくても大丈夫。\n\n"
                "来てくれたことに気づく。\n今している話を短く伝える。\n気軽に参加できる質問を置く。\n\n"
                "この順番なら、見ているだけの人も入りやすい。\n"
                "配信は最初の一言で、空気がかなり変わる。"
            ),
            (
                "配信の時間を増やしても疲れてしまうなら、回数より設計を見直したい。\n\n"
                "無理なく話せる長さ。\n休める曜日。\n振り返る時間。\n次回の準備に使える余白。\n\n"
                "自分が続けられる形を作ると、配信の質も初見への返し方も保ちやすい。"
            ),
            (
                "コメントが少ない日は、配信が向いていないと決めなくていい。\n\n"
                "入った人に挨拶できたか。\n話題が一方通行になっていないか。\n返しやすい質問を置けたか。\n\n"
                "確認する場所があると、数字だけで気持ちを振り回されにくい。\n"
                "次の配信で一つ試せば十分。"
            ),
            (
                "ライバーを始める前に、誰かのやり方を全部真似する必要はない。\n\n"
                "自分が話しやすいテーマ。\n続けやすい時間。\n無理なく返せるコメントの量。\n\n"
                "ここを自分に合わせる方が、配信は長く続きやすい。\n"
                "最初は自分の話しやすさを見つける時間にしていい。"
            ),
            (
                "配信で常連が増えてきた時ほど、初見が置いていかれないか見ておきたい。\n\n"
                "内輪の話が長くなりすぎない。\n今の話題を時々説明する。\n初めてのコメントも拾う。\n\n"
                "新しく来た人が参加できると、配信全体の空気もやわらかくなる。"
            ),
            (
                "配信が終わったあとに疲れ切ってしまうなら、頑張り方を増やす前に減らせるものを探したい。\n\n"
                "長すぎる配信。\n準備しすぎる企画。\n全部のコメントに完璧に返そうとすること。\n\n"
                "続けるためには、余裕を残すことも大事。\n"
                "無理の少ない形の方が、見ている人にも自然な空気が伝わる。"
            ),
            (
                "ライバー事務所を比べる時は、始める前の説明だけで判断しない方がいい。\n\n"
                "困った時に誰へ聞けるか。\n配信後に振り返れるか。\n自分の生活に合う進め方を考えてくれるか。\n\n"
                "続けるほど迷いは出てくるから、相談のしやすさまで見て選ぶと安心しやすい。"
            ),
            (
                "配信で自信がなくなった時は、他の人の数字だけを見続けない方がいい。\n\n"
                "昨日より挨拶ができた。\n前よりコメントを拾えた。\n終わり方を決められた。\n\n"
                "自分の変化を見つけられると、続ける理由が少しずつ増えていく。\n"
                "配信は一回ごとの完璧さより、続けた中で作る空気が大事。"
            ),
            (
                "初見がコメントしやすい配信は、答えを急がせない。\n\n"
                "好きな食べ物みたいな軽い質問。\n二択で答えられる話題。\n見ているだけでも大丈夫という一言。\n\n"
                "参加のハードルを下げると、会話は少しずつ始まりやすい。\n"
                "気軽に入れる空気を作ることが、次のコメントにつながる。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    else:
        variants = [
            (
                "夜職で店を選ぶ時、時給だけで決める子はけっこう危ない。\n\n"
                "時給が高くても、客層が合わない。\n"
                "ノルマがきつい。\n"
                "出勤ペースが合わない。\n"
                "担当に相談しづらい。\n"
                "雰囲気が自分に合わない。\n\n"
                "このどれかがズレると、結局続かない。\n\n"
                "大事なのは、条件が良い店じゃなくて、自分が続けられる店を選ぶこと。\n\n"
                "迷っているなら、入る前に一回整理した方がいい。"
            ),
            (
                "夜職を始める前に見てほしいのは、時給よりも続けられる条件。\n\n"
                "家から遠すぎないか。\n"
                "出勤ペースに無理がないか。\n"
                "客層が自分に合いそうか。\n"
                "困った時に担当へ相談できるか。\n\n"
                "ここを見ないまま入ると、条件は良いのにしんどい店になることがある。\n\n"
                "焦って決めるより、先に自分が無理なく働ける形を整理した方がいい。"
            ),
            (
                "夜職でしんどくなる子は、入店前に確認するポイントが少ないことが多い。\n\n"
                "時給はいくらか。\n"
                "ノルマはあるか。\n"
                "客層は合いそうか。\n"
                "出勤ペースに無理はないか。\n"
                "困った時に誰へ相談できるか。\n\n"
                "ここを曖昧にしたまま入ると、条件が良くても続かないことがある。\n"
                "店選びは勢いより、先に不安を整理する方が大事。"
            ),
            (
                "キャバで働く時、合わない店を選ぶと自分の努力だけではどうにもならないことがある。\n\n"
                "客層が合わない。\n"
                "担当に相談しづらい。\n"
                "出勤の圧が強い。\n"
                "ノルマの感覚が合わない。\n\n"
                "こういうズレは、入ってから気づくとかなりしんどい。\n\n"
                "だから時給だけじゃなく、自分が続けられる環境かを見ること。\n"
                "迷うなら入る前に一度整理した方がいい。"
            ),
            (
                "夜職を副業で考えている子ほど、無理な出勤ペースで決めない方がいい。\n\n"
                "本業の疲れが残る。\n"
                "生活リズムが崩れる。\n"
                "寝不足で接客がきつくなる。\n"
                "続ける前に気持ちが折れる。\n\n"
                "副業で大事なのは、頑張れる店より続けられる店。\n"
                "条件を見る時は、時給と同じくらい自分の生活に合うかを見た方がいい。"
            ),
            (
                "移籍を考える時は、今の店が嫌だからだけで決めるとまた同じことで悩みやすい。\n\n"
                "何が合わなかったのか。\n"
                "客層なのか、担当なのか、ノルマなのか。\n"
                "出勤ペースなのか、店の雰囲気なのか。\n\n"
                "ここを整理しないまま次を選ぶと、条件が変わっても悩みは残る。\n\n"
                "移籍は逃げじゃなくて、合う環境を選び直すこと。\n"
                "だから先に理由をはっきりさせた方がいい。"
            ),
            (
                "夜職で担当に相談しづらい店は、条件が良くても長く続けにくい。\n\n"
                "出勤を増やしたい時。\n"
                "客層が合わない時。\n"
                "ノルマがきつい時。\n"
                "メンタルが落ちている時。\n\n"
                "こういう時に話せる人がいないと、一人で抱え込むことになる。\n\n"
                "店選びでは時給だけじゃなく、困った時に相談できる環境かも見てほしい。"
            ),
            (
                "夜職を始めるか迷っているなら、最初に決めるべきなのは店名より自分の優先順位。\n\n"
                "稼ぎたい金額。\n"
                "出勤できる曜日。\n"
                "避けたい客層。\n"
                "無理したくない条件。\n"
                "相談しやすい担当の有無。\n\n"
                "ここが決まっていないと、条件だけ良く見える店に流されやすい。\n"
                "先に自分の軸を作る方が、あとで後悔しにくい。"
            ),
            (
                "キャバで売上に悩む時、根性だけでどうにかしようとすると苦しくなる。\n\n"
                "客層が合っているか。\n"
                "席で無理しすぎていないか。\n"
                "同伴や指名の流れを作れているか。\n"
                "担当に相談できているか。\n\n"
                "売上は気合いだけじゃなく、環境とやり方で変わる部分がある。\n"
                "一人で抱え込む前に、どこが詰まっているか整理した方がいい。"
            ),
            (
                "夜職で続く子は、最初から強い子ばかりじゃない。\n\n"
                "無理な店を選ばない。\n"
                "合わない条件を我慢しすぎない。\n"
                "困った時に相談する。\n"
                "自分の生活リズムを崩しすぎない。\n\n"
                "このあたりを守っている子の方が、結果的に長く続きやすい。\n\n"
                "強くなるより先に、続けられる環境を選ぶことが大事。"
            ),
            (
                "夜職でお店の空気が合わないと、条件が良くても毎回出勤が重くなる。\n\n"
                "女の子同士の雰囲気。\n"
                "黒服との距離感。\n"
                "お客さんの層。\n"
                "出勤の相談しやすさ。\n\n"
                "このあたりは求人の条件だけでは見えにくい。\n"
                "入る前に、続けられる空気かどうかも見た方がいい。"
            ),
            (
                "夜職で罰金やノルマがきつい店は、時給が高く見えても手元に残りにくいことがある。\n\n"
                "遅刻や欠勤の扱い。\n"
                "同伴や指名の圧。\n"
                "売上が落ちた時の対応。\n"
                "相談できる担当がいるか。\n\n"
                "ここを知らないまま入ると、思ったよりしんどくなる。\n"
                "条件を見る時は、引かれるものまで確認した方がいい。"
            ),
            (
                "夜職をしながら副業や次の仕事を考えるなら、今の働き方を無理に広げすぎない方がいい。\n\n"
                "出勤を増やしすぎる。\n"
                "睡眠を削る。\n"
                "休む時間がなくなる。\n"
                "考える余裕がなくなる。\n\n"
                "将来の選択肢を作るには、今の生活を壊さないことも大事。\n"
                "稼ぎ方と続け方はセットで見た方がいい。"
            ),
            (
                "スカウトを選ぶ時は、紹介できる店の数より話を聞いてくれるかを見た方がいい。\n\n"
                "希望の出勤ペース。\n"
                "苦手な客層。\n"
                "避けたい条件。\n"
                "今の悩み。\n\n"
                "ここを聞かずに店だけ出してくる人だと、入ってからズレやすい。\n"
                "相談しやすさは、店選びと同じくらい大事。"
            ),
            (
                "夜職でメンタルが落ちる時は、自分が弱いからとは限らない。\n\n"
                "客層が合わない。\n"
                "担当に相談できない。\n"
                "ノルマが重い。\n"
                "生活リズムが崩れている。\n\n"
                "環境が合っていないだけで、気持ちが削られることは普通にある。\n"
                "我慢する前に、何がしんどいのか整理した方がいい。"
            ),
            (
                "夜職の体験入店で見るべきなのは、最初に聞いた時給だけじゃない。\n\n"
                "待機中の空気。\n女の子同士の距離感。\n黒服が忙しい時の対応。\n初めてのお客さんにつく時のフォロー。\n\n"
                "短い時間でも、働きやすさは意外と見える。\n"
                "条件と同じくらい、自分が安心して出勤できそうかを見て決めた方がいい。"
            ),
            (
                "夜職を始める時、最初の一ヶ月を頑張りすぎると後から苦しくなりやすい。\n\n"
                "出勤を詰めすぎる。\n慣れない接客で睡眠を削る。\n相談せずに抱え込む。\n\n"
                "最初は環境に慣れることも大事な仕事。\n"
                "無理なく続くペースを作れた子の方が、焦らず次の目標を考えられる。"
            ),
            (
                "夜職でお客さんとの距離感に悩むなら、最初から無理に合わせすぎない方がいい。\n\n"
                "連絡が負担になっていないか。\n自分の生活を崩していないか。\n嫌なことを断れずにいないか。\n\n"
                "接客は頑張るほど大事だけど、続けるための線引きも同じくらい大事。\n"
                "店を選ぶ時は、担当に相談しながら自分が守れる働き方を決めておくと迷いにくい。"
            ),
            (
                "夜職で収入を安定させたいなら、出勤日数だけ増やせばいいわけじゃない。\n\n"
                "自分に合う客層か。\n無理なく話せる接客か。\n休めるペースになっているか。\n相談できる人がいるか。\n\n"
                "続けられる土台がある方が、毎月の波も小さくなりやすい。"
            ),
            (
                "移籍先を探す時は、今の不満を一つずつ言葉にしてから動くと選びやすい。\n\n"
                "出勤のこと。\n客層のこと。\nノルマのこと。\n担当とのやり取りのこと。\n\n"
                "次の店に求めるものがはっきりすると、条件だけで焦って決めにくくなる。"
            ),
            (
                "夜職を副業にするなら、周りが働いている日数をそのまま真似しなくていい。\n\n"
                "本業との両立。\n睡眠の確保。\n急な予定への対応。\n気持ちに余裕が残るか。\n\n"
                "自分の生活を守れる出勤ペースの方が、結局は長く続けやすい。"
            ),
            (
                "夜職で指名が増えない時、会話の上手さだけを責めなくていい。\n\n"
                "お客さんと会える席につけているか。\n自分に合う接客ができる店か。\n次につながる連絡が負担になっていないか。\n\n"
                "やり方と環境が合っていないだけで、苦しくなることはある。\n"
                "一人で結論を急がず、詰まっている場所を見直した方がいい。"
            ),
            (
                "夜職で求人を見る時は、良いことだけが並んでいるほど確認する項目を増やした方がいい。\n\n"
                "出勤の決め方。\nノルマや罰金の扱い。\n客層の傾向。\n困った時の相談先。\n\n"
                "入ってから聞いていなかったとなるより、最初に質問できる方が安心して働ける。"
            ),
            (
                "夜職を続けるか迷う時は、辞めたい気持ちだけで決める前に原因を分けてみてほしい。\n\n"
                "店が合わないのか。\n出勤ペースがきついのか。\n接客に疲れているのか。\n生活リズムが崩れているのか。\n\n"
                "原因が違えば、変えるべきことも違う。\n"
                "自分を責める前に、続け方を選び直す余地がないか見てみるのも大事。"
            ),
            (
                "夜職で相談する相手を選ぶ時は、急かしてくる人より希望を聞いてくれる人を見た方がいい。\n\n"
                "今すぐ決めたいのか。\n避けたい条件はあるか。\n出勤できる日はいつか。\n不安に思っていることは何か。\n\n"
                "ここを飛ばして進めると、あとで無理が出やすい。\n"
                "自分のペースで選べる環境を大事にしてほしい。"
            ),
        ]
        text = variants[(index - 1) % len(variants)]
    return build_generation_output(
        internal_analysis=f"account={account_id}; deterministic reader-facing template; index={index}",
        public_post_text=text,
        safety_notes="Public text only. Internal analysis must not be posted.",
        blocked_reasons=[],
    )


def _topic_from_signal(account_id: str, signal: str) -> str:
    """Classify private reference/transcript content without quoting it publicly."""
    text = str(signal or "")
    if account_id == "night_scout":
        mapping = [
            (("時給", "条件", "罰金"), "conditions"),
            (("ノルマ", "売上", "指名"), "pressure"),
            (("客層", "雰囲気", "お店"), "fit"),
            (("移籍", "辞め", "転職"), "transfer"),
            (("副業", "出勤", "生活", "睡眠"), "balance"),
        ]
    else:
        mapping = [
            (("初見", "入室", "コメント"), "first_viewer"),
            (("ギフト", "応援", "投げ銭"), "support"),
            (("時間", "継続", "習慣"), "consistency"),
            (("企画", "話題", "会話"), "conversation"),
            (("事務所", "相談", "サポート"), "support_system"),
        ]
    for words, topic in mapping:
        if any(word in text for word in words):
            return topic
    return "general"


def generate_grounded_reader_facing_post(
    account_id: str,
    *,
    private_signal: str,
    index: int = 1,
    media_metadata: dict[str, Any] | None = None,
    slot_theme: str = "",
    recent_posts: list[str] | None = None,
) -> dict[str, Any]:
    """Build a new public caption from private evidence without exposing it."""
    topic = _topic_from_signal(account_id, private_signal)
    metadata = dict(media_metadata or {})
    recent = [extract_public_post_text(item) for item in (recent_posts or []) if extract_public_post_text(item)]
    seed = hashlib.sha256(
        f"{account_id}|{topic}|{slot_theme}|{private_signal}|{index}".encode("utf-8")
    ).hexdigest()
    choice = int(seed[:8], 16)
    if account_id == "night_scout":
        hooks = {
            "conditions": ["夜職の店選びは、時給だけ高ければ安心とは限らない。", "条件が良く見える店ほど、数字の外側も確認しておきたい。"],
            "pressure": ["売上や指名が苦しい時、全部を自分の努力不足にしなくていい。", "夜職で気持ちが削られる時は、頑張り方より環境を見直したい。"],
            "fit": ["続けやすい店かどうかは、条件表だけではわからない。", "店選びで後悔しにくい子は、働く場面まで想像している。"],
            "transfer": ["移籍を考え始めたら、次の店より先に今の悩みを整理したい。", "店を変えたい理由が曖昧なままだと、同じ悩みを繰り返しやすい。"],
            "balance": ["副業で夜職を続けるなら、出勤数より生活を守れるかが大事。", "稼ぐ予定を立てる時ほど、休める予定も一緒に決めたい。"],
            "general": ["夜職で迷った時は、不安を曖昧なままにしない方がいい。", "店を決める前に、自分が続けられる条件を整理しておきたい。"],
        }
        criteria = {
            "conditions": "ノルマや控除の扱い、出勤の自由度、客層との相性まで見ると、手元に残るものと続けやすさが見えてくる。",
            "pressure": "相談できる担当がいるか、無理な出勤になっていないか、売上以外の負担が増えていないかを一つずつ見る。",
            "fit": "客層、店の空気、出勤相談のしやすさ。毎回の出勤で困りそうな場面を先に確かめる。",
            "transfer": "客層、出勤の圧、相談しづらさなど、今つらい理由を分けると、次に避けたい条件がはっきりする。",
            "balance": "睡眠、本業、休む日まで含めて無理のないペースを決めると、短期で消耗しにくい。",
            "general": "条件、客層、出勤、相談のしやすさを分けて考えると、自分に必要な基準が見えやすい。",
        }
        endings = [
            "焦って決めるより、自分が無理なく続けられるかを入る前に確認した方がいい。",
            "良い条件を探すだけでなく、自分に合う働き方を選ぶことが長く続ける近道になる。",
        ]
        text = f"{hooks.get(topic, hooks['general'])[choice % 2]}\n\n{criteria.get(topic, criteria['general'])}\n\n{endings[(choice // 2) % 2]}"
        concepts = {
            "conditions": ["compensation", "work_conditions", "fit"], "pressure": ["pressure", "support", "workload"],
            "fit": ["customers", "workplace_fit", "consultation"], "transfer": ["transfer", "decision_criteria", "fit"],
            "balance": ["side_job", "sleep", "sustainable_schedule"], "general": ["anxiety", "decision_criteria", "sustainability"],
        }
    else:
        hooks = {
            "first_viewer": ["初見がすぐ抜ける時は、面白さより入りやすさを見直したい。", "配信の最初の数秒で、初見が会話に入れるかは大きく変わる。"],
            "support": ["応援を増やしたい時ほど、お願いより関係づくりを先にしたい。", "ギフトの前に、また来たいと思える配信になっているかを見直したい。"],
            "consistency": ["配信を続けられる人は、毎回の気合いだけに頼っていない。", "伸び悩む時ほど、続けられる配信の型を作ることが大事。"],
            "conversation": ["話題が続かない時、すごい話を用意する必要はない。", "コメントが少ない時は、会話へ入る入口を増やしてみたい。"],
            "support_system": ["ライバー事務所は、条件より困った時に相談できるかを見たい。", "配信を始める前に、数字が落ちた時の支え方まで確認しておきたい。"],
            "general": ["配信が伸びない時は、才能より参加しやすい空気を見直したい。", "初見が残る配信は、入りやすさの小さな工夫ができている。"],
        }
        criteria = {
            "first_viewer": "入室に気づく、今の話題を短く伝える、答えやすい質問を置く。この3つで初見は会話へ入りやすくなる。",
            "support": "コメントを丁寧に拾い、常連だけで固めず、次も参加しやすい空気を作ると応援は育ちやすい。",
            "consistency": "無理のない時間帯、話しやすいテーマ、終了後の短い振り返りを決めると数字が揺れても続けやすい。",
            "conversation": "今日の小さな出来事や答えやすい質問を置くと、見る側も話すきっかけを作りやすい。",
            "support_system": "生活に合う配信設計や、伸びない時の改善を一緒に考えてくれるかまで見ると選びやすい。",
            "general": "初見への声かけ、コメントの拾い方、次回につながる終わり方を一つずつ整える。",
        }
        endings = [
            "配信は一人で話し切る場ではなく、見ている人が参加できる余白を作る場。",
            "大きく変えなくても、入りやすさを一つ改善するだけで次の配信は変わっていく。",
        ]
        text = f"{hooks.get(topic, hooks['general'])[choice % 2]}\n\n{criteria.get(topic, criteria['general'])}\n\n{endings[(choice // 2) % 2]}"
        concepts = {
            "first_viewer": ["first_viewer", "participation", "comments"], "support": ["community", "support", "retention"],
            "consistency": ["schedule", "reflection", "sustainability"], "conversation": ["conversation", "questions", "participation"],
            "support_system": ["agency_selection", "consultation", "improvement"], "general": ["entry_experience", "comments", "retention"],
        }
    source_similarity = round(difflib.SequenceMatcher(None, str(private_signal or ""), text).ratio(), 4)
    recent_similarity = round(max((difflib.SequenceMatcher(None, item, text).ratio() for item in recent), default=0.0), 4)
    validation = final_public_post_validator(text, account_id)
    output = build_generation_output(
        internal_analysis=f"grounded topic={topic}; account={account_id}; composition={choice % 4}",
        public_post_text=text,
        safety_notes="Private evidence was reduced to safe concepts. Raw evidence and identifiers are excluded.",
        blocked_reasons=validation.get("blocked_reasons", []),
    )
    output.update({
        "grounding_summary": {
            "topic": topic,
            "concepts": concepts.get(topic, concepts["general"]),
            "signal_length_bucket": "long" if len(str(private_signal or "")) >= 400 else "medium" if len(str(private_signal or "")) >= 120 else "short",
            "media_type": str(metadata.get("media_type", "unknown")),
            "slot_theme": str(slot_theme or "general"),
        },
        "transformation_summary": "abstracted concepts, recomposed hook, criteria, rationale and reader action",
        "similarity_score": source_similarity,
        "recent_post_similarity_score": recent_similarity,
        "validator_result": validation["status"],
    })
    return output


def reader_facing_template_count(account_id: str) -> int:
    """Number of deterministic public templates available for fallback rotation."""
    return 25


def last_posted_account(posted_rows: list[dict[str, Any]], rotation_accounts: list[str]) -> str:
    latest: tuple[datetime, str] | None = None
    allowed = set(rotation_accounts)
    for row in posted_rows:
        account_id = str(row.get("account_id", ""))
        if account_id not in allowed:
            continue
        if str(row.get("platform", "")).lower() not in {"", "threads"}:
            continue
        if str(row.get("status", "")).upper() not in {"POSTED", "RECOVERED", ""}:
            continue
        raw = str(row.get("posted_at") or row.get("created_at") or row.get("collected_at") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.min.replace(tzinfo=timezone.utc)
        if latest is None or dt > latest[0]:
            latest = (dt, account_id)
    return latest[1] if latest else ""


def account_rotation_order(
    accounts: list[str],
    config: dict[str, Any],
    posted_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    rotation = config.get("account_rotation_strategy", {})
    enabled = bool(rotation.get("account_rotation_enabled", False))
    rotation_accounts = [a for a in rotation.get("rotation_accounts", accounts) if a in accounts]
    if not enabled or not rotation_accounts:
        return {"enabled": False, "ordered_accounts": accounts, "selected_account": accounts[0] if accounts else "", "skipped_accounts": []}
    last = last_posted_account(posted_rows or [], rotation_accounts)
    if not last:
        last = str(rotation.get("last_posted_account_hint_for_dry_run", ""))
    if last in rotation_accounts and len(rotation_accounts) > 1:
        preferred = [a for a in rotation_accounts if a != last] + [last]
    else:
        preferred = rotation_accounts
    rest = [a for a in accounts if a not in preferred]
    ordered = preferred + rest
    return {
        "enabled": True,
        "strategy": rotation.get("rotation_strategy", "alternate_by_last_posted_account"),
        "last_posted_account": last,
        "ordered_accounts": ordered,
        "selected_account": ordered[0] if ordered else "",
        "skipped_accounts": [{"account_id": a, "reason": "account_rotation_not_first"} for a in ordered[1:]],
        "fallback_to_available_account": bool(rotation.get("fallback_to_available_account", True)),
    }


def public_preview(text: str, limit: int = 260) -> str:
    text = extract_public_post_text(text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."
