#!/usr/bin/env python3
"""Apply the V29 voice policy and register ten review-only candidates.

This command never publishes and never uploads media.  It reads the historical
V27/V28 queue rows only to preserve their source/media provenance, then writes
new WAITING_REVIEW rows with new identifiers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from config_loader import get_config  # noqa: E402
from gemini_hybrid_client import GeminiHybridClient  # noqa: E402
from public_post_quality import canonical_voice_profile, final_public_post_validator  # noqa: E402
from sheets_client import TAB_DEFINITIONS, make_client  # noqa: E402

TARGET_SHEET_ID = "1ZlBE0l2DF_A50Q3IApWTAQtNPTWfaa4lxaz8s9q2ljU"
RUN_ID = "voice_v29_20260816"

ROUTES: dict[str, list[tuple[str, str]]] = {
    "night_scout": [
        ("direct_reference_media", "キャバのお客さんへの接客で、ラストコールの痛客接客編に出てくるひめかさんの返しが印象に残った。\n\n和田さんから『愛してるゲーム』を振られても否定せず、そのまま次の会話につなげてるんだよね。\n\n僕が接客で見るのもここ。無理に盛り上げるより、店の空気を止めずに一度受けて次へ運べるかが大事だよ。"),
        ("reference_text_generation", "現役キャバ嬢にこれだけは伝えたい\n\n急な話題にすぐ正解・不正解を返すより、一回受けてから質問を返せる子の方が接客は安定するんだよね。客層が変わっても、この力は使える。\n\n僕が見るのは、店の空気を切らずに会話を次へ運べるか。苦手な話題を無理に盛り上げなくていい。まず一言受ける、この切り替えが大事だよ。"),
        ("pdca_text_generation", "夜職の時給の見方で迷ってる子に伝えたい\n\n前回、時給と控除後の手取りを整理した投稿は表示102件、いいね1件だった。僕は『結局いくら残るのか』が具体的だったから、自分ごとで読まれたんだと思う。\n\n次は控除前後の差を一例に絞る。表示といいねがどう変わるかを見るよ。"),
        ("new_text_generation", "これからキャバやりたい子は、体入前に時給だけで決めない方がいい。\n\n僕が一番見るのは『週何回なら無理なく続けられるか』なんだよね。早上がり、ノルマの締め日、控除、客層で、同じ時給でも手取りと疲れ方はかなり変わる。\n\n担当には、週2出勤で早上がりが続いた月の手取り例まで聞いておく。ここが働き方に合う店を選ぶのが大事だよ。"),
        ("approved_source_clip", "店選びで周りの評判だけを信じると、入ってからズレることって結構ある。\n\n一条響さんが『みんなが右でも、自分が左だと思えば左を選ぶ』って話してるの、夜職の店選びにもそのまま当てはまるんだよね。\n\n僕なら評判より、出勤条件・客層・担当との相性を自分で見る。自分の基準で決めた方が、あとで納得できると思う。"),
    ],
    "liver_manager": [
        ("direct_reference_media", "初見バトルのあと、せっかく出会えた人との会話がそこで終わるのはもったいないよね。\n\nこの動画は、配信の悩みに答えながら初見さんとの距離をどう縮めるかが分かりやすい。\n\n私なら次の配信で、バトル後に一つだけ質問を続けてみるかな。『普段どんな配信を見る？』くらいで大丈夫。次も来やすい入口を残してみてね。"),
        ("reference_text_generation", "応援してくれる人がいるのに枠が重くなる時って、『誰が一番支えてるか』を競わせてることがあるんだよね。\n\n古参だけの話、ギフト額の比較、注意をリスナー任せにする。この3つが続くと、初見さんは入りづらい。\n\n次の配信では内輪話をひとつだけ減らしてみて。私なら、みんなが答えられる質問を一つ置くかな。そこから枠の空気は変えられるよ。"),
        ("pdca_text_generation", "前回のコメント導線の投稿は、表示5件、いいね0件、コメント0件だった。\n\n私なら『声をかける』だけじゃなく、そのまま使える一言まで見せるかな。初見さんは返し方が分かるから、コメントしやすいんだよね。\n\n次の配信では『今○○の話をしてるよ』を一例にして、表示とコメントがどう変わるか試してみる。"),
        ("new_text_generation", "コメントが止まると、話題を増やさなきゃって焦るよね。\n\nでも『今日どうだった？』より、『今日は忙しかった？ゆっくりできた？』の二択の方が、初見さんも返しやすい。\n\n私なら冒頭10分で使う二択を3つだけ用意するかな。全部変えなくて大丈夫。答えやすい入口を一つ作るだけで、会話は始まりやすくなるよ。"),
        ("approved_source_clip", "ライバー自身が配信企画を考える前に、何を届けたいか言葉にできると迷いにくいんだよね。\n\nこの動画では、目標や経験、好きなことを聞いてから、次の面談で企画を一緒に考える流れが紹介されてる。\n\n私ならまず『誰に、何を届けたい？』を一文だけ書いてみるかな。目的が見えると、次の配信で試す企画も選びやすくなるよ。"),
    ],
}

SEMANTIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision", "voice_persona", "voice_persona_score", "identity_fit",
        "interpersonal_distance", "register_fit", "conversational_naturalness",
        "persona_specific_tone", "reasons",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["PASS", "REJECT"]},
        "voice_persona": {"type": "string", "enum": ["PASS", "FAIL"]},
        "voice_persona_score": {"type": "integer", "minimum": 0, "maximum": 100},
        "identity_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "interpersonal_distance": {"type": "string", "enum": ["PASS", "FAIL"]},
        "register_fit": {"type": "string", "enum": ["PASS", "FAIL"]},
        "conversational_naturalness": {"type": "string", "enum": ["PASS", "FAIL"]},
        "persona_specific_tone": {"type": "string", "enum": ["PASS", "FAIL"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_tone(account_id: str) -> str:
    if account_id == "night_scout":
        return "男性スカウト / 僕 / casual-professional / plain-conversational majority / scout field judgment / direct to cabaret women / formal-business tone prohibited"
    return "女性LIVE manager / 私 / warm conversational / feminine older-sister feel / non-desu-masu-dominant / concrete next-stream coaching / stereotyped feminine speech prohibited"


def generation_mode(route: str) -> str:
    return {
        "reference_text_generation": "reference_text",
        "pdca_text_generation": "metrics_driven_pdca_text",
        "new_text_generation": "original_text",
    }.get(route, route)


def old_queue_id(account_id: str, route: str) -> str:
    return f"q_acceptance_v27_20260812_{account_id}_{route}"


def queue_id(account_id: str, route: str) -> str:
    return f"q_{RUN_ID}_{account_id}_{route}"


def _records(client: Any, tab: str) -> list[dict[str, Any]]:
    return [dict(row) for row in client._ws(tab).get_all_records()]


def _append(client: Any, tab: str, row: dict[str, Any]) -> None:
    ws = client._ws(tab)
    headers = ws.row_values(1)
    ws.append_row([str(row.get(name, "")) for name in headers], value_input_option="USER_ENTERED")


def _posted_hash(rows: list[dict[str, Any]]) -> str:
    value = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def semantic_review(client: GeminiHybridClient, *, account_id: str, route: str, text: str, source_url: str) -> dict[str, Any]:
    profile = canonical_voice_profile(account_id)
    payload = {
        "public_candidate_text": text,
        "source_url": source_url,
        "source_summary": f"V29 {route} candidate; source facts/provenance are retained in Sheets.",
        "account_id": account_id,
        "persona": profile,
    }
    prompt = (
        "公開候補の声だけを厳格に審査してください。内容の良し悪しとは分離し、identity、読者との距離、"
        "register、会話としての自然さ、アカウント固有のpersonaを判定します。"
        "Night Scoutは男性スカウトの僕・現場口調、Liver Managerは女性マネージャーの私・温かい伴走口調です。"
        "です・ます中心の報告書調、コンサル調、誤った一人称はFAILです。\n"
        f"RESTRICTED_PAYLOAD={json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    )
    response = client.generate_json(
        model=os.environ.get("GEMINI_REVIEW_MODEL", "gemini-2.5-flash-lite"),
        prompt=prompt,
        schema=SEMANTIC_SCHEMA,
        operation="v29_voice_review",
        account_id=account_id,
        cache_context={"run_id": RUN_ID, "route": route, "text_hash": hashlib.sha256(text.encode()).hexdigest()},
    )
    return dict(response["data"])


def build_matrix(
    *,
    semantic_client: GeminiHybridClient | None = None,
    source_urls: dict[tuple[str, str], str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for account_id, candidates in ROUTES.items():
        for route, text in candidates:
            validation = final_public_post_validator(text, account_id)
            voice = validation["voice_persona_check"]
            assert validation["status"] == "PASS", (account_id, route, validation)
            assert int(validation["public_post_quality_score"]) >= 85, (account_id, route, validation)
            semantic = (
                semantic_review(
                    semantic_client,
                    account_id=account_id,
                    route=route,
                    text=text,
                    source_url=str((source_urls or {}).get((account_id, route), "")),
                )
                if semantic_client else {
                    "decision": "DRY_RUN_NOT_CALLED",
                    "voice_persona": "NOT_CALLED",
                    "voice_persona_score": 0,
                }
            )
            if semantic_client:
                required_passes = (
                    "voice_persona", "identity_fit", "interpersonal_distance", "register_fit",
                    "conversational_naturalness", "persona_specific_tone",
                )
                assert semantic.get("decision") == "PASS", (account_id, route, semantic)
                assert all(semantic.get(field) == "PASS" for field in required_passes), (account_id, route, semantic)
                assert int(semantic.get("voice_persona_score", 0)) >= 85, (account_id, route, semantic)
            rows.append({
                "account_id": account_id,
                "route": route,
                "public_post_text": text,
                "validation": validation,
                "semantic": semantic,
                "queue_id": queue_id(account_id, route),
            })
    return rows


def _upsert_policy_rows(client: Any) -> None:
    at = now_iso()
    account_ws = client._ws("accounts")
    account_headers = account_ws.row_values(1)
    account_rows = account_ws.get_all_records()
    for account_id in ROUTES:
        row_number = next(i for i, row in enumerate(account_rows, start=2) if str(row.get("account_id")) == account_id)
        notes = str(account_rows[row_number - 2].get("notes", ""))
        marker = f"canonical_voice=account_voice_profiles_v1:{account_id}"
        client._batch_update_fields(
            account_ws,
            account_headers,
            row_number,
            {"tone": canonical_tone(account_id), "notes": (notes + " | " + marker).strip(" |")},
            label=f"accounts:{account_id}:v29",
        )

    prompt_ws = client._ws("prompt_templates")
    prompt_rows = prompt_ws.get_all_records()
    for account_id in ROUTES:
        template_id = f"{account_id}_threads_voice_v29"
        if not any(str(row.get("template_id")) == template_id for row in prompt_rows):
            profile = canonical_voice_profile(account_id)
            _append(client, "prompt_templates", {
                "template_id": template_id,
                "account_id": account_id,
                "template_name": template_id,
                "version": "v29-2026-08-16",
                "purpose": "Threads投稿生成",
                "prompt_text": profile.get("prompt_contract", ""),
                "active": "FALSE",
                "created_at": at,
                "notes": "Canonical sentence-level voice policy; history preserved; activation requires owner review.",
            })

    learning_rows = _records(client, "learning_rules")
    for account_id in ROUTES:
        rule_id = f"voice_v29_{account_id}"
        if not any(str(row.get("rule_id")) == rule_id for row in learning_rows):
            _append(client, "learning_rules", {
                "rule_id": rule_id,
                "account_id": account_id,
                "insight_type": "canonical_account_voice",
                "content": canonical_tone(account_id),
                "confidence": "1.0",
                "applied_count": "0",
                "created_at": at,
                "active": "FALSE",
                "auto_apply": "FALSE",
                "status": "WAITING_REVIEW",
            })


def apply(client: Any, matrix: list[dict[str, Any]]) -> dict[str, Any]:
    for tab in ("accounts", "prompt_templates", "learning_rules", "queue", "publication_review"):
        client._ensure_tab(tab, TAB_DEFINITIONS[tab])
    posted_before = _records(client, "posted_results")
    posted_hash_before = _posted_hash(posted_before)
    _upsert_policy_rows(client)

    queue_rows = _records(client, "queue")
    queue_by_id = {str(row.get("queue_id", "")): row for row in queue_rows}
    for item in matrix:
        account_id = item["account_id"]
        route = item["route"]
        qid = item["queue_id"]
        if qid in queue_by_id:
            continue
        source = deepcopy(queue_by_id.get(old_queue_id(account_id, route), {}))
        if not source:
            raise RuntimeError(f"historical_provenance_queue_missing:{account_id}:{route}")
        validation = item["validation"]
        voice = validation["voice_persona_check"]
        details = voice["details"]
        semantic = item["semantic"]
        source.update({
            "queue_id": qid,
            "draft_id": "",
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": "threads",
            "status": "WAITING_REVIEW",
            "auto_publish": "FALSE",
            "generation_mode": generation_mode(route),
            "content_route": route,
            "public_post_text": item["public_post_text"],
            "generated_by": "voice_v29_canonical_matrix",
            "validator_status": "PASS",
            "internal_leak_status": "PASS",
            "account_fit_status": "PASS",
            "public_post_quality_score": validation["public_post_quality_score"],
            "reader_value_score": validation["reader_value_score"],
            "naturalness_score": validation["naturalness_score"],
            "cta_pressure_score": validation["cta_pressure_score"],
            "voice_persona_status": voice["status"],
            "voice_persona_score": semantic["voice_persona_score"],
            "polite_ending_ratio": details["business_polite_ratio"],
            "first_person_status": details["first_person_status"],
            "formal_consultant_penalty": details["formal_consultant_penalty"],
            "conversational_style_score": details["conversational_style_score"],
            "feminine_warmth_score": details["feminine_warmth_score"],
            "voice_blocked_reasons": "[]",
            "generation_policy_json": json.dumps({"v29_voice_semantic_review": semantic}, ensure_ascii=False, sort_keys=True),
            "canary_id": f"canary_{RUN_ID}_{account_id}_{route}",
            "human_review_decision": "",
            "human_reviewed_at": "",
            "human_review_note": "",
            "error": "",
            "blocked_reason": "",
            "rejected_reason": "",
            "processed_at": "",
            "posted_at": "",
            "post_url": "",
            "result_id": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })
        _append(client, "queue", source)
        _append(client, "publication_review", {
            "review_id": f"review_{RUN_ID}_{account_id}_{route}",
            "queue_id": qid,
            "account_id": account_id,
            "platform": "threads",
            "post_type": route,
            "queue_status": "WAITING_REVIEW",
            "review_status": "WAITING_REVIEW",
            "public_post_text": item["public_post_text"],
            "media_asset_id": source.get("media_asset_id", ""),
            "media_preview_url": source.get("media_url", ""),
            "media_type": source.get("media_type", ""),
            "source_url": source.get("source_url", ""),
            "primary_topic": source.get("primary_topic", ""),
            "validator_status": "PASS",
            "internal_leak_status": "PASS",
            "account_fit_status": "PASS",
            "topic_coherence_status": source.get("topic_coherence_status", "PASS"),
            "batch_diversity_status": source.get("batch_diversity_status", "PASS"),
            "voice_persona_status": voice["status"],
            "voice_persona_score": semantic["voice_persona_score"],
            "polite_ending_ratio": details["business_polite_ratio"],
            "first_person_status": details["first_person_status"],
            "formal_consultant_penalty": details["formal_consultant_penalty"],
            "conversational_style_score": details["conversational_style_score"],
            "feminine_warmth_score": details["feminine_warmth_score"],
            "voice_blocked_reasons": "[]",
            "media_validator_status": source.get("media_validator_status", "PASS"),
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

    queue_after = {str(row.get("queue_id", "")): row for row in _records(client, "queue")}
    review_after = {str(row.get("queue_id", "")): row for row in _records(client, "publication_review")}
    for item in matrix:
        qid = item["queue_id"]
        assert queue_after[qid]["public_post_text"] == item["public_post_text"]
        assert str(queue_after[qid]["status"]) == "WAITING_REVIEW"
        assert str(queue_after[qid]["voice_persona_status"]) == "VOICE_PERSONA_PASS"
        assert review_after[qid]["public_post_text"] == item["public_post_text"]

    for account_id in ROUTES:
        account = next(row for row in _records(client, "accounts") if str(row.get("account_id")) == account_id)
        assert account["tone"] == canonical_tone(account_id)
        prompt = next(row for row in _records(client, "prompt_templates") if str(row.get("template_id")) == f"{account_id}_threads_voice_v29")
        assert str(prompt["active"]).upper() == "FALSE"
        rule = next(row for row in _records(client, "learning_rules") if str(row.get("rule_id")) == f"voice_v29_{account_id}")
        assert str(rule["active"]).upper() == "FALSE" and str(rule["auto_apply"]).upper() == "FALSE"
        assert str(rule["status"]).upper() == "WAITING_REVIEW"

    posted_after = _records(client, "posted_results")
    assert len(posted_before) == len(posted_after)
    assert posted_hash_before == _posted_hash(posted_after)
    return {
        "status": "PASS",
        "queue_read_after_write": 10,
        "review_read_after_write": 10,
        "posted_results_unchanged": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-voice-v29", action="store_true")
    parser.add_argument("--output", default="/private/tmp/v29-voice-correction-result.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and not args.confirm_voice_v29:
        raise SystemExit("BLOCKED: --apply requires --confirm-voice-v29")
    client = None
    source_urls: dict[tuple[str, str], str] = {}
    if args.apply:
        cfg = get_config()
        if cfg["sheet_id"] != TARGET_SHEET_ID:
            raise RuntimeError("production_sheet_id_mismatch")
        client = make_client(cfg, dry_run=False)
        current_queue = {str(row.get("queue_id", "")): row for row in _records(client, "queue")}
        source_urls = {
            (account_id, route): str(current_queue.get(old_queue_id(account_id, route), {}).get("source_url", ""))
            for account_id, candidates in ROUTES.items()
            for route, _text_value in candidates
        }
    semantic_client = GeminiHybridClient() if args.apply else None
    matrix = build_matrix(semantic_client=semantic_client, source_urls=source_urls)
    result: dict[str, Any] = {"status": "DRY_RUN_PASS", "matrix": matrix}
    if args.apply:
        assert client is not None
        result.update(apply(client, matrix))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "candidate_count": len(matrix),
        "would_publish": False,
        "would_upload": False,
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
