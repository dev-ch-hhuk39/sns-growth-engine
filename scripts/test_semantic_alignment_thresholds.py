#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generation.semantic_alignment import LocalSemanticAlignmentProvider

SOURCE = "配信に初見が入っても、常連だけで会話していると参加しづらい。今話しているテーマを伝えるとコメントのきっかけを作れる。"
PUBLIC = "配信に初見さんが来ても、常連だけの会話が続くと入りづらさを感じやすい。\n\n最初に今の話題を一言伝えると、コメントするきっかけを作れます。\n\n初見が参加しやすい入口を、配信の最初に用意してみてください。"
CLAIMS = ["常連だけの会話は初見が参加しづらい", "テーマを伝えるとコメントのきっかけになる"]
SUPPORT = [
    {"caption_claim": "常連だけの会話が続くと入りづらい", "source_evidence": "常連だけで会話していると参加しづらい"},
    {"caption_claim": "今の話題を伝えるとコメントのきっかけになる", "source_evidence": "今話しているテーマを伝えるとコメントのきっかけを作れる"},
]

provider = LocalSemanticAlignmentProvider()
passed = provider.evaluate(source_text=SOURCE, public_post_text=PUBLIC, main_claims=CLAIMS, claim_support=SUPPORT, recent_posts=[])
copied = provider.evaluate(source_text=SOURCE, public_post_text=SOURCE, main_claims=CLAIMS, claim_support=SUPPORT, recent_posts=[])

DRIFT_SOURCE = (
    "そういうところで投げても、"
    "すごいと思うかもしれないけど、"
    "楽しくないと思う。"
)
DRIFT_PUBLIC = (
    "ライバーとして迷った時は、"
    "変えることを一度に増やしすぎない方がいい。"
    "\n\n"
    "初見への説明、コメントの拾い方、"
    "終わり方を分けて確認する。"
    "\n\n"
    "全部を直そうとせず、"
    "一番困っている場所から整えてみましょう。"
)
DRIFT_CLAIMS = [
    "変えることを一度に増やしすぎない方がいい",
    "初見への説明とコメントの拾い方を確認する",
    "一番困っている場所から整える",
]
DRIFT_SUPPORT = [
    {
        "caption_claim": (
            "一番困っている場所から整える"
        ),
        "source_evidence": DRIFT_SOURCE,
    }
]

drifted = provider.evaluate(
    source_text=DRIFT_SOURCE,
    public_post_text=DRIFT_PUBLIC,
    main_claims=DRIFT_CLAIMS,
    claim_support=DRIFT_SUPPORT,
    recent_posts=[],
)

checks = [
    ("grounded transformed caption passes", passed.status == "PASS"),
    ("coverage threshold is met", (passed.data or {}).get("main_claim_coverage", 0) >= 0.70),
    ("unsupported claims are zero", (passed.data or {}).get("unsupported_claim_count") == 0),
    ("source copy is blocked", copied.status == "BLOCKED" and "source_copy_similarity_above_threshold" in (copied.data or {}).get("blocked_reasons", [])),
    (
        "weak claim-to-evidence match is blocked",
        drifted.status == "BLOCKED"
        and "unsupported_claims_present"
        in (drifted.data or {}).get(
            "blocked_reasons",
            [],
        ),
    ),
    (
        "unlisted caption claims reduce coverage",
        (drifted.data or {}).get(
            "main_claim_coverage",
            1,
        )
        < 0.70,
    ),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
failed = [name for name, ok in checks if not ok]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
