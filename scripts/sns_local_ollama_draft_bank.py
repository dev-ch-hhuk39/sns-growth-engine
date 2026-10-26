#!/usr/bin/env python3
"""Local Mac Ollama drafts. Never publish, approve, or write to Google Sheets."""
from __future__ import annotations

import argparse
from collections import Counter
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
STATE = Path.home() / ".cache" / "chadult-sns-local-drafts"
URL = "http://127.0.0.1:11434/api/generate"
ACCOUNTS = ("night_scout", "liver_manager")
MODEL = "gemma4:e4b"
JST = timezone(timedelta(hours=9))
TOPICS = {
    "night_scout": ("夜職の店選び", "勤務条件の確認", "接客の負担", "生活リズム", "転職の相談"),
    "liver_manager": ("配信準備", "視聴者との会話", "継続するコツ", "振り返り", "配信環境"),
}


def normalize(s: str) -> str:
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE).lower()


def validate(text: str, history: list[str], forbidden: list[str]) -> str:
    normalized = normalize(text)
    if not 50 <= len(text) <= 380:
        return "LENGTH"
    if any(normalize(word) in normalized for word in forbidden if normalize(word)):
        return "FORBIDDEN"
    if "https://" in text or "http://" in text or "www." in text:
        return "LINK"
    if any(pattern in text for pattern in ("絶対に", "必ず儲かる", "100%", "誰でも稼げる", "月収100万円")):
        return "CLAIM"
    if any(
        normalized == normalize(old)
        or difflib.SequenceMatcher(None, normalized, normalize(old)).ratio() >= 0.80
        for old in history
    ):
        return "DUPLICATE"
    return "PASS"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Local Ollama results must never cause an HTTP redirect or egress."""
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ValueError("LOCAL_INFERENCE_REDIRECT_BLOCKED")


def generate(account: str, config: dict, count: int, batch: int) -> list:
    from public_post_quality import canonical_voice_prompt
    topic = TOPICS[account][batch % len(TOPICS[account])]
    prompt = (
        "必ずJSONオブジェクトのposts配列にhookとbodyの日本語文字列を入れて返答。"
        f"Threadsの投稿案を{count}件作る。"
        f"書き手: {config.get('persona', '')} / 文体: {config.get('tone', '')}。"
        f"正式な口調: {canonical_voice_prompt(account)}。"
        f"テーマ: {topic}。切り口番号:{batch}。"
        "本文は2〜4文、60〜230文字。少し具体的で読者が試せる助言。"
        "実際に経験した、実績が出た、誰もが稼げる等の捏造と保証をしない。"
        "医療法律金融に関する事実の断定、広告主張、URL、PR文を避ける。"
        "同じ型を繰り返さず、各案の論点と例を変える。"
        "各案は一つの論点に絞り、冒頭の問いに本文と結論で答える。"
        "読者が置かれる具体的な場面、判断する理由、次に試せる行動を自然に書く。"
        "内部ルール名や審査結果、架空の実績は本文に書かない。"
        f"禁止語: {json.dumps((config.get('forbidden_keywords') or [])[:18], ensure_ascii=False)}"
    )
    payload = {
        "model": MODEL, "stream": False, "format": "json", "think": False,
        "prompt": prompt, "options": {"temperature": 0.75, "num_predict": 1400},
    }
    request = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=130) as response:
            if response.status != 200:
                return []
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            return []
        result = json.loads(raw)
        parsed = json.loads(str(result.get("response") or ""))
        posts = parsed.get("posts")
        return posts[:count] if isinstance(posts, list) else []
    except (OSError, TimeoutError, ValueError, TypeError):
        return []


def read_existing(account: str, folder: Path) -> tuple[list[dict], list[str]]:
    file = folder / (account + "-pending-qa.json")
    if file.is_symlink():
        raise ValueError("SYMLINK")
    if not file.exists():
        return [], []
    d = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(d, dict) or d.get("account_id") != account:
        raise ValueError("INVALID_EXISTING")
    rows = d.get("candidates")
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("INVALID_RECORD_COUNT")
    return rows, [str(x.get("draft_text") or "") for x in rows if isinstance(x, dict)]


def save(account: str, rows: list[dict], folder: Path) -> None:
    target = folder / (account + "-pending-qa.json")
    if folder.is_symlink() or not folder.is_dir() or folder.stat().st_mode & 0o022 or target.is_symlink():
        raise ValueError("UNSAFE_STORAGE")
    body = {"schema": "sns_ollama_drafts_v1", "account_id": account,
            "status": "PENDING_HUMAN_QA", "canonical_bank_ready": False,
            "generated_at": datetime.now(JST).isoformat(), "candidates": rows}
    fd, name = tempfile.mkstemp(prefix=".private-drafts.", suffix=".tmp", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(body, out, ensure_ascii=False, indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, target)
        dirfd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def local_quality(account: str, text: str, history: list[str]) -> tuple[bool, list[str]]:
    sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
    from public_post_quality import final_public_post_validator
    from generation_quality_gates import evaluate_generation_quality
    from generation.content_quality_v2 import hard_gate
    public = final_public_post_validator(text, account)
    hard = hard_gate({'account_id': account, 'target_account_id': account,
                     'platform': 'threads', 'public_post_text': text, 'supported_claims': []},
                     account_id=account, public_validation=public)
    quality = evaluate_generation_quality(account, text, history, batch_compared=history)
    codes = sorted(set(public['blocked_reasons'] + hard['hard_gate_reasons']
                       + quality.get('diversity_blocked_reasons', [])
                       + quality.get('topic_blocked_reasons', [])))
    return all(r['status'] == 'PASS' for r in (public, hard, quality)), codes


def run(account: str, target: int, folder: Path = STATE, *, require_quality: bool = False) -> dict:
    os.umask(0o077)
    if account not in ACCOUNTS or not 1 <= target <= 40:
        raise ValueError("INVALID_SCOPE")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if folder.is_symlink() or folder.stat().st_mode & 0o022:
        raise ValueError("INVALID_PRIVATE_DIR")
    cfg = json.loads((ROOT / "config/accounts" / (account + ".json")).read_text(encoding="utf-8"))
    rows, history = read_existing(account, folder)
    forbidden = cfg.get("forbidden_keywords") or []
    rejected, batches = 0, 0
    quality_reasons: Counter[str] = Counter()
    while len(rows) < target and batches < 25:
        needed = min(4, target - len(rows))
        for post in generate(account, cfg, needed, batches):
            if not isinstance(post, dict):
                rejected += 1
                continue
            text = (str(post.get("hook") or "").strip() + "\n" +
                    str(post.get("body") or "").strip()).strip()
            if validate(text, history, forbidden) != "PASS":
                rejected += 1
                continue
            if require_quality:
                passed, reasons = local_quality(account, text, history)
                if not passed:
                    quality_reasons.update(reasons)
                    rejected += 1
                    continue
            key = hashlib.sha256((account + "|" + normalize(text)).encode()).hexdigest()[:24]
            rows.append({
                "draft_id": "local_" + key, "account_id": account,
                "post_type": "original_text", "draft_text": text,
                "workflow_status": "PENDING_HUMAN_QA", "canonical_bank_ready": False,
                "source": "local_ollama_unverified",
                "requires": ["editorial_review", "factual_review", "global_duplicate_scan",
                             "slot_compatibility", "final_publisher_gate"],
            })
            history.append(text)
            if len(rows) >= target:
                break
        batches += 1
        if batches % 3 == 0:
            save(account, rows, folder)
    save(account, rows, folder)
    result = {"account": account, "draft_count": len(rows), "target": target,
            "rejected": rejected, "model_calls": batches, "status": "PENDING_HUMAN_QA",
            "ready_count": 0, "posts": 0, "paid_api_calls": 0, "sheets_writes": 0}
    if require_quality:
        result['quality_rejection_counts'] = dict(sorted(quality_reasons.items()))
        # Recheck every saved record, including resumed files. This is local
        # evidence only and cannot grant historical novelty or approval.
        result['local_qa'] = review_existing(account, folder) if rows else {'draft_count': 0}
    return result



def _read_private_pending(path: Path) -> bytes:
    """Bound the read and reject links before consuming private source data."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        meta = os.fstat(source.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
                or meta.st_mode & 0o077 or meta.st_size > 2_000_000):
            raise ValueError("LOCAL_QA_SOURCE_NOT_PRIVATE_REGULAR")
        raw = source.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("LOCAL_QA_SOURCE_TOO_LARGE")
    return raw


def review_existing(account: str, folder: Path = STATE) -> dict:
    """Read-only production-rule QA; never turns a local idea into approval.

    Only account-scoped pending files are accepted. The result contains fixed
    codes/counts/indexes, not private text or claimed approval/provenance.
    Historical/global duplicates and runtime publisher joins remain unchecked.
    """
    if (account not in ACCOUNTS or folder.is_symlink() or not folder.is_dir()
            or folder.stat().st_mode & 0o077):
        raise ValueError("LOCAL_QA_SCOPE_INVALID")
    path = folder / (account + "-pending-qa.json")
    raw = _read_private_pending(path)
    before = hashlib.sha256(raw).digest()
    source = json.loads(raw)
    if (not isinstance(source, dict) or source.get("schema") != "sns_ollama_drafts_v1"
            or source.get("account_id") != account
            or source.get("status") != "PENDING_HUMAN_QA"
            or source.get("canonical_bank_ready") is not False):
        raise ValueError("LOCAL_QA_SOURCE_NOT_PENDING")
    rows = source.get("candidates")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("LOCAL_QA_COUNT_INVALID")
    ids = []
    for row in rows:
        if (not isinstance(row, dict) or row.get("account_id") != account
                or row.get("workflow_status") != "PENDING_HUMAN_QA"
                or row.get("canonical_bank_ready") is not False
                or row.get("post_type") != "original_text"
                or row.get("source") != "local_ollama_unverified"
                or not isinstance(row.get("draft_text"), str) or not row["draft_text"].strip()
                or not isinstance(row.get("draft_id"), str) or not row["draft_id"]):
            raise ValueError("LOCAL_QA_CANDIDATE_SCOPE_INVALID")
        ids.append(row["draft_id"])
    if len(set(ids)) != len(ids):
        raise ValueError("LOCAL_QA_ID_AMBIGUOUS")
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
    from public_post_quality import final_public_post_validator
    from generation_quality_gates import evaluate_generation_quality
    from generation.content_quality_v2 import hard_gate

    results = []
    reasons: Counter[str] = Counter()
    for index, row in enumerate(rows):
        text = row["draft_text"]
        others = [item["draft_text"] for i, item in enumerate(rows) if i != index]
        public = final_public_post_validator(text, account)
        # Ignore any caller-supplied supported_claims/approval fields: these
        # original ideas have no independently verified factual evidence.
        hard = hard_gate({"account_id": account, "target_account_id": account,
                          "platform": "threads", "public_post_text": text,
                          "supported_claims": []}, account_id=account, public_validation=public)
        individual = evaluate_generation_quality(account, text, others, batch_compared=[])
        batch = evaluate_generation_quality(account, text, others, batch_compared=others)
        codes = sorted(set(public["blocked_reasons"] + hard["hard_gate_reasons"]
                           + batch.get("diversity_blocked_reasons", [])
                           + batch.get("topic_blocked_reasons", [])))
        reasons.update(codes)
        results.append({"index": index, "public_status": public["status"],
                        "hard_gate_status": hard["status"],
                        "individual_quality_status": individual["status"],
                        "whole_batch_quality_status": batch["status"], "reason_codes": codes})
    # A changed source cannot receive a receipt bound to the earlier content.
    if hashlib.sha256(_read_private_pending(path)).digest() != before:
        raise ValueError("LOCAL_QA_SOURCE_CHANGED")
    return {"mode": "QA_ONLY", "account": account, "qa_completed": True,
            "status": "PENDING_HUMAN_QA", "draft_count": len(rows),
            "public_validation_pass": sum(r["public_status"] == "PASS" for r in results),
            "hard_gate_pass": sum(r["hard_gate_status"] == "PASS" for r in results),
            "individual_local_checks_pass": sum(all(r[k] == "PASS" for k in
                ("public_status", "hard_gate_status", "individual_quality_status")) for r in results),
            "whole_batch_checks_pass": sum(all(r[k] == "PASS" for k in
                ("public_status", "hard_gate_status", "whole_batch_quality_status")) for r in results),
            "reason_counts": dict(sorted(reasons.items())), "candidates": results,
            "original_unchanged": True, "canonical_bank_ready": False,
            "global_duplicate_scan": "NOT_PERFORMED", "runtime_publisher_check": "NOT_PERFORMED",
            "ready_count": 0, "model_calls": 0, "posts": 0, "paid_api_calls": 0, "sheets_writes": 0}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--account", choices=ACCOUNTS, required=True)
    p.add_argument("--target", type=int, default=24)
    p.add_argument("--qa-only", action="store_true", help="Read existing pending drafts; no generation or writes")
    p.add_argument("--qualified-only", action="store_true", help="Generate into a separate private reserve with unchanged local quality gates")
    a = p.parse_args()
    try:
        if a.qa_only and a.qualified_only:
            raise ValueError('QA_GENERATION_MODE_CONFLICT')
        if a.qa_only:
            result = review_existing(a.account, STATE)
            print("SNS_LOCAL_OLLAMA_DRAFT_QA=" + json.dumps(result, sort_keys=True), flush=True)
            return 0  # QA completion is never production acceptance.
        if a.qualified_only:
            result = run(a.account, a.target, STATE / 'quality-reserve', require_quality=True)
        else:
            result = run(a.account, a.target)
        print("SNS_LOCAL_OLLAMA_DRAFT_BANK=" + json.dumps(result, sort_keys=True), flush=True)
        complete = result["draft_count"] >= a.target
        if a.qualified_only:
            complete = complete and result['local_qa'].get('whole_batch_checks_pass') == result['draft_count']
        return 0 if complete else 2
    except Exception:
        prefix = "SNS_LOCAL_OLLAMA_DRAFT_QA" if a.qa_only else "SNS_LOCAL_OLLAMA_DRAFT_BANK"
        print(prefix + "=BLOCKED reason=UNVERIFIED_RUNTIME posts=0", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
