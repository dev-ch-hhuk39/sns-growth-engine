#!/usr/bin/env python3
from generation_quality_gates import (
    TOPIC_CONFIDENCE_MIN,
    evaluate_generation_quality,
)


def check(condition: bool, name: str) -> None:
    assert condition, name


shared = "焦って決めるより、自分が無理なく続けられるかを入る前に確認した方がいい。"
blocked = evaluate_generation_quality(
    "night_scout",
    f"店選びでは条件を整理したい。\n\n{shared}",
    [{"account_id": "night_scout", "queue_id": "q_old", "public_post_text": f"移籍前に悩みを分けたい。\n\n{shared}"}],
)
check(blocked["status"] == "BLOCKED", "exact shared closing blocks")
check(blocked["shared_closing_detected"], "shared closing evidence")
check(blocked["shared_sentence_count"] == 1, "shared sentence count")

punctuation = evaluate_generation_quality(
    "night_scout",
    "条件を比べる前に手取りを確認する。\n\n焦って決めるより 自分が無理なく続けられるかを入る前に確認した方がいい！",
    [{"account_id": "night_scout", "public_post_text": f"条件の見え方だけで決めない。\n\n{shared}"}],
)
check(punctuation["shared_closing_detected"], "punctuation-only change blocks")

suffix_change = evaluate_generation_quality(
    "night_scout",
    "条件を比べる前に手取りを確認する。\n\n焦って決めるより、自分が無理なく続けられるかを入る前に確認しておきたい。",
    [{"account_id": "night_scout", "public_post_text": f"条件の見え方だけで決めない。\n\n{shared}"}],
)
check(suffix_change["shared_closing_detected"], "suffix-only change blocks")

cross_account = evaluate_generation_quality(
    "night_scout",
    "夜職の条件は時給と控除を分けて確認したい。\n\n手取りを比べてから無理なく続けられる店を選びたい。",
    [{"account_id": "liver_manager", "public_post_text": "夜職の条件は時給と控除を分けて確認したい。\n\n手取りを比べてから無理なく続けられる店を選びたい。"}],
)
check(cross_account["batch_diversity_status"] == "PASS", "different accounts are not compared")

mixed = evaluate_generation_quality(
    "liver_manager",
    "ライバー事務所は困った時に相談できる支え方を確認したい。\n\n初見が入ったらコメントを拾うと会話へ参加しやすくなる。\n\n所属先は数字が落ちた時にも相談できる場所を選びたい。",
    [],
)
check(mixed["topic_coherence_status"] == "BLOCKED", "agency and first-viewer topics block")
check(mixed["off_topic_sentence_count"] >= 1, "off-topic sentence evidence")

closing_mismatch = evaluate_generation_quality(
    "liver_manager",
    "初見が入りやすい配信は最初の挨拶がわかりやすい。\n\n入室に気づいて短い質問を置く。\n\n事務所は相談できる所属先を選びたい。",
    [],
)
check("conclusion_topic_mismatch" in closing_mismatch["topic_blocked_reasons"], "closing topic mismatch")

media_mismatch = evaluate_generation_quality(
    "liver_manager",
    "事務所を選ぶ時は困った時に相談できるかを確認したい。\n\n数字が落ちた時の支え方まで聞いておく。",
    [],
    visual_text="初見が入ったらコメントで質問して会話へ参加してもらう",
)
check("media_text_topic_mismatch" in media_mismatch["topic_blocked_reasons"], "media topic mismatch")

community_visual_alignment = evaluate_generation_quality(
    "liver_manager",
    (
        "枠が崩れそうって配信者が1番感じてるからこそ、"
        "リスナー皆んなでで支えなきゃいけない！"
    ),
    [],
    visual_text=(
        "枠主にリスナーがついてこないと、"
        "初見さんは一生増えない。"
    ),
)
check(
    TOPIC_CONFIDENCE_MIN == 0.70,
    "topic threshold is not relaxed",
)
check(
    community_visual_alignment["status"] == "PASS",
    "community and first-viewer evidence pass",
)
check(
    community_visual_alignment["primary_topic"]
    == "community_building",
    "community topic inferred",
)
check(
    community_visual_alignment["topic_confidence"]
    >= TOPIC_CONFIDENCE_MIN,
    "community text confidence passes unchanged threshold",
)
check(
    community_visual_alignment["visual_topic_match"],
    "community visual family matches",
)
check(
    community_visual_alignment["visual_topic_confidence"]
    >= TOPIC_CONFIDENCE_MIN,
    "community visual confidence passes unchanged threshold",
)

aligned = evaluate_generation_quality(
    "liver_manager",
    "初見が入りやすい配信は最初の挨拶がわかりやすい。\n\n入室に気づき、今の話題を短く伝えて答えやすい質問を置く。\n\n次の配信では初見が参加できる入口を一つ整えたい。",
    [],
)
check(aligned["status"] == "PASS", "related first-viewer and comment topics pass")
check(aligned["primary_topic"] == "first_viewer_retention", "primary topic inferred")

unresolved = evaluate_generation_quality(
    "liver_manager",
    "今日は少し考え方を変えてみたい。\n\n無理をせず一つずつ進めていく。",
    [],
)
check("primary_topic_unresolved" in unresolved["topic_blocked_reasons"], "unresolved topic blocks")


# Broad historical formats are not a reason to block; structural repetition is
# enforced only against sibling candidates in the same generation batch.
historical_structure = {
    "account_id": "night_scout",
    "queue_id": "historical_structure",
    "public_post_text": (
        "移籍を考えた時は、今の店で困っている理由を整理したい。\n\n"
        "客層と出勤の負担、担当へ相談できるかを分けて確認する。\n\n"
        "次の店では同じ悩みを繰り返さない条件を選びたい。"
    ),
}
structure_candidate = (
    "夜職で数字に追われた時は、努力量より負担の偏りを確認したい。\n\n"
    "売上だけでなく、無理な出勤や同伴が増えていないかを確かめる。\n\n"
    "指名の悩みは環境と接客の両方から見直して決めたい。"
)
history_only = evaluate_generation_quality(
    "night_scout",
    structure_candidate,
    [historical_structure],
    primary_topic="performance_pressure",
)
check("batch_structure_reused" not in history_only["diversity_blocked_reasons"], "historical structure alone does not block")

sibling_structure = evaluate_generation_quality(
    "night_scout",
    structure_candidate,
    [historical_structure],
    batch_compared=[historical_structure],
    primary_topic="performance_pressure",
)
check("batch_structure_reused" in sibling_structure["diversity_blocked_reasons"], "same-batch structure blocks")
check(sibling_structure["structure_compared_candidate_ids"] == ["historical_structure"], "structure evidence identifies sibling")

pressure_topic = evaluate_generation_quality(
    "night_scout",
    (
        "頑張っているのに苦しい時は、売上だけで自分を責めない方がいい。\n\n"
        "指名と同伴の負担が偏っていないかを整理する。\n\n"
        "指名の悩みは環境と接客の両方から見直して決めたい。"
    ),
    [],
    primary_topic="performance_pressure",
)
check(pressure_topic["topic_coherence_status"] == "PASS", "preferred primary wins a supported tie")
check(pressure_topic["closing_topic"] == "performance_pressure", "closing resolves to explicit primary when evidenced")

low_confidence = evaluate_generation_quality(
    "night_scout",
    (
        "店選びでは時給と客層と担当と売上と睡眠を全部確認したい。\n\n"
        "条件、雰囲気、相談、指名、出勤を同じように見直す。\n\n"
        "最後は時給を確認して決めたい。"
    ),
    [],
    primary_topic="work_conditions",
)
check("primary_topic_confidence_below_threshold" in low_confidence["topic_blocked_reasons"], "low topic confidence blocks")


# Production retry contract: five attempts must rotate fresh topics/components,
# and at least one must escape the exact legacy hook/body that triggered the canary block.
from public_post_quality import generate_production_post

legacy_rows = [{
    "account_id": "night_scout",
    "queue_id": "legacy_conditions",
    "public_post_text": (
        "条件が良く見える店ほど、数字の外側も確認しておきたい。\n\n"
        "ノルマや控除の扱い、出勤の自由度、客層との相性まで見ると、手元に残るものと続けやすさが見えてくる。\n\n"
        "焦って決めるより、自分が無理なく続けられるかを入る前に確認した方がいい。"
    ),
}]
retry_results = []
for attempt in range(5):
    candidate = generate_production_post(
        "night_scout",
        batch_id="retry_contract_batch",
        content_type="original_text",
        recent_posts=[legacy_rows[0]["public_post_text"]],
        attempt=attempt,
    )
    retry_results.append(evaluate_generation_quality(
        "night_scout",
        candidate["public_post_text"],
        legacy_rows,
        primary_topic=candidate.get("grounding_summary", {}).get("quality_topic", ""),
    ))
check(any(item["status"] == "PASS" for item in retry_results), "retry rotation escapes legacy composition")
check(len({generate_production_post("night_scout", batch_id="retry_contract_batch", content_type="original_text", attempt=i)["public_post_text"] for i in range(5)}) == 5, "five attempts produce five distinct texts")

print("PASS test_generation_quality_gates.py")
