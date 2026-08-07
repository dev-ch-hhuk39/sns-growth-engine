#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


gate_path = Path("scripts/hybrid_ai_gate.py")
text = gate_path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''SCHEDULED_TEXT_TYPES = {
    "original_text",
    "reference_text",
    "pdca_text",
    "metrics_driven_pdca_text",
}''',
    '''SCHEDULED_TEXT_TYPES = {
    "original_text",
    "reference_text",
    "pdca_text",
    "metrics_driven_pdca_text",
    "direct_reference_media",
}''',
    "scheduled type block",
)

text = replace_once(
    text,
    '''def _review_prompt(
    queue: Mapping[str, Any],
    source_text: str,
    candidate_text: str,
    policy: Mapping[str, Any],
) -> str:
    return (
        "公開直前のSNS投稿を厳格に審査してください。自然な日本語、参照根拠への忠実性、"
        "対象読者・アカウント適合、公開安全性を確認してください。誤字、重複助詞、[音楽]等、"
        "定型句、根拠不明の収益額、他社宣伝、BtoB/BtoC不一致はREJECTしてください。\\n\\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\\n"
        f"QUEUE_ID={_text(queue.get('queue_id'))}\\n"
        f"SOURCE_EVIDENCE={source_text}\\n"
        f"CANDIDATE_TEXT={candidate_text}"
    )''',
    '''def _review_prompt(
    queue: Mapping[str, Any],
    source_text: str,
    candidate_text: str,
    policy: Mapping[str, Any],
) -> str:
    pdca_instruction = ""
    if (
        _scheduled_text_type(queue) in {"pdca_text", "metrics_driven_pdca_text"}
        and _text(queue.get("generation_mode")).lower() == "metrics_driven_pdca_text"
    ):
        pdca_instruction = (
            "この候補はPDCA枠です。SOURCE_EVIDENCEにある公開済み自社投稿の表示数、いいね数、"
            "コメント数、再投稿数、引用数は、反応を説明するために意図的に使う公開可能な実測根拠です。"
            "これらの公開投稿パフォーマンス値だけを理由にINTERNAL_PROCESS_METRICSやaccount_fit不一致として"
            "REJECTしないでください。ただし秘密情報、非公開の社内KPI、運用手順、認証情報は引き続きREJECTしてください。"
        )
    return (
        "公開直前のSNS投稿を厳格に審査してください。自然な日本語、参照根拠への忠実性、"
        "対象読者・アカウント適合、公開安全性を確認してください。誤字、重複助詞、[音楽]等、"
        "定型句、根拠不明の収益額、他社宣伝、BtoB/BtoC不一致はREJECTしてください。"
        f"{(' ' + pdca_instruction) if pdca_instruction else ''}\\n\\n"
        f"ACCOUNT_POLICY={json.dumps(policy, ensure_ascii=False, sort_keys=True)}\\n"
        f"QUEUE_ID={_text(queue.get('queue_id'))}\\n"
        f"SOURCE_EVIDENCE={source_text}\\n"
        f"CANDIDATE_TEXT={candidate_text}"
    )''',
    "review prompt",
)

text = replace_once(
    text,
    '        if route.route == "new_text_generation":\n',
    '        if route.route in {"new_text_generation", "owned_media_transform"}:\n',
    "scheduled contract route guard",
)

gate_path.write_text(text, encoding="utf-8")


test_path = Path("scripts/test_scheduled_preview_post_ai_contract.py")
test = test_path.read_text(encoding="utf-8")

test = replace_once(
    test,
    'class ContractClient:\n',
    '''class PromptCaptureClient:
    def __init__(self, generated_text: str) -> None:
        self.generated_text = generated_text
        self.actual_request_count = 0
        self.review_prompt = ""

    def generate_json(self, **kwargs: Any) -> dict[str, Any]:
        self.actual_request_count += 1
        operation = kwargs["operation"]
        if operation == "classify":
            data = {
                "decision": "PASS",
                "target_account_match": "PASS",
                "target_audience_match": "PASS",
                "source_audience": "night_work_job_seeker",
                "commercial_context": "B2C",
                "source_usage_fit": "PASS",
                "risk_flags": [],
                "reasons": [],
            }
        elif operation == "generate":
            data = {
                "public_post_text": self.generated_text,
                "preserved_facts": [],
                "removed_noise": [],
                "notes": "fixture",
            }
        else:
            self.review_prompt = kwargs["prompt"]
            data = {
                "decision": "PASS",
                "natural_japanese": "PASS",
                "source_grounding": "PASS",
                "account_fit": "PASS",
                "public_safety": "PASS",
                "risk_flags": [],
                "reasons": [],
            }
        return {"data": data, "actual_requests": 1, "cache_hit": False}


class ContractClient:
''',
    "prompt capture client",
)

test = replace_once(
    test,
    'assert original_result.generation["scheduled_text_contract"]["status"] == "REPAIRED"\n\n',
    '''assert original_result.generation["scheduled_text_contract"]["status"] == "REPAIRED"

# Scheduled owned Direct media must preserve the Night Scout first-person voice after AI rewriting.
direct_queue = queue("night_scout", "direct_reference_media", night_current)
direct_queue.update({
    "generation_mode": "direct_reference_media",
    "media_origin": "direct_reference",
    "ownership": "system_owned",
    "source_id": "system_owned_night_scout_fixture",
})
direct_context = context(night_current)
direct_context["permission_evidence_status"] = "APPROVED"
direct_result = HybridAiGate(ContractClient(night_generated_without_boku)).evaluate(
    direct_queue,
    direct_context,
)
assert direct_result.status == "PASS", direct_result.audit()
assert "僕" in direct_result.public_post_text, direct_result.public_post_text
assert direct_result.generation["scheduled_text_contract"]["status"] == "REPAIRED"

''',
    "direct regression assertion",
)

test = replace_once(
    test,
    'assert "pdca_measured_observation_missing" in contract["rejected_generated_contract_reasons"]\n\n',
    '''assert "pdca_measured_observation_missing" in contract["rejected_generated_contract_reasons"]

# Owned public-post metrics are intentional evidence for PDCA, not secret internal process metrics.
prompt_client = PromptCaptureClient(pdca_generic)
prompt_result = HybridAiGate(prompt_client).evaluate(
    queue("night_scout", "pdca_text", pdca_current),
    context(pdca_current),
)
assert prompt_result.status == "PASS", prompt_result.audit()
assert "公開済み自社投稿" in prompt_client.review_prompt, prompt_client.review_prompt
assert "INTERNAL_PROCESS_METRICS" in prompt_client.review_prompt, prompt_client.review_prompt
assert "秘密情報" in prompt_client.review_prompt, prompt_client.review_prompt

''',
    "PDCA prompt regression assertion",
)

test_path.write_text(test, encoding="utf-8")
print("PR141_FINAL_SELF_FIX_APPLIED=PASS")
