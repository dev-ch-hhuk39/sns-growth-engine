#!/usr/bin/env python3
"""Read-only-first reconciliation of duplicate-blocked canaries to real Threads evidence."""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; sys.path[:0]=[str(ROOT/"scripts"),str(ROOT/"src")]
from build_live_canary_inventory import build_inventory
from metrics_collection_schedule import build_metric_collection_jobs
from process_threads_queue import append_row, records, update_row

VALID_VERIFY={"PASS","VERIFIED","READ_AFTER_WRITE_PASS"}
REQUIRED_CANARIES=tuple(
 (account, kind)
 for account in ("night_scout", "liver_manager")
 for kind in ("original_text", "reference_text", "direct_image", "direct_carousel", "direct_video", "approved_source_clip")
)
def truthy(v: Any)->bool: return str(v).lower() in {"1","true","yes"}
def token(account:str)->str: return os.getenv(f"THREADS_ACCESS_TOKEN_{account.upper()}","")
def api_permalink(account:str, post_id:str)->str:
    if not token(account) or not post_id: return ""
    try:
        import requests
        r=requests.get(f"https://graph.threads.net/v1.0/{post_id}",params={"fields":"permalink","access_token":token(account)},timeout=12); r.raise_for_status()
        return str(r.json().get("permalink") or "")
    except Exception: return ""
def live(client:Any)->dict[str,list[dict[str,Any]]]:
    tabs=("queue","source_posts","source_post_media","media_permissions","source_videos","video_clip_candidates","media_assets","posted_results","metrics_collection_jobs")
    return {t:[dict(x) for x in client._ws(t).get_all_records()] for t in tabs}
def classify(c:dict[str,Any], rows:list[dict[str,Any]])->dict[str,Any]:
    account=str(c["account_id"]); kind=str(c["canary_type"]); text=str(c.get("public_post_text","")).strip()
    matches=[r for r in rows if str(r.get("account_id",""))==account and str(r.get("posted_text","")).strip()==text and str(r.get("status","")).upper()=="POSTED"]
    r=matches[-1] if matches else {}; reasons=[]
    if not r: reasons=["no_matching_posted_result"]
    else:
        if not truthy(r.get("real_post")): reasons.append("not_real_post")
        if not str(r.get("external_post_id","")).strip() or not str(r.get("post_url","")).strip(): reasons.append("missing_permalink_or_external_id")
        if str(r.get("verification_status","")).upper() not in VALID_VERIFY: reasons.append("posted_results_read_after_write_missing")
        media=kind not in {"original_text","reference_text"}
        if media and not truthy(r.get("media_used")): reasons.append("media_missing")
        if not media and truthy(r.get("media_used")): reasons.append("unexpected_media")
        if kind=="direct_video" and str(r.get("source_post_id", "")) != str(c.get("source_post_id", "")): reasons.append("direct_video_source_mismatch")
        if kind=="approved_source_clip" and str(r.get("clip_candidate_id", "")) != str(c.get("clip_candidate_id", "")): reasons.append("clip_candidate_mismatch")
        if kind in {"direct_image","direct_video"} and str(c.get("media_asset_id", "")) and str(r.get("media_asset_id", "")) != str(c.get("media_asset_id", "")): reasons.append("media_asset_mismatch")
        actual=api_permalink(account, str(r.get("external_post_id", "")))
        if not actual: reasons.append("actual_permalink_verify_required")
        elif actual != str(r.get("post_url", "")): reasons.append("actual_permalink_mismatch")
    status="EXISTING_CANARY_VALID" if r and not reasons else ("VERIFY_REQUIRED" if "actual_permalink_verify_required" in reasons and len(reasons)==1 else "EXISTING_CANARY_INVALID")
    fields={k:r.get(k,"") for k in ("result_id","external_post_id","post_url","posted_at","posted_text","real_post","media_used","media_asset_id","media_url","source_post_id","source_video_id","clip_candidate_id")}
    actual_type="text" if not truthy(r.get("media_used")) else ("approved_source_clip" if str(r.get("clip_candidate_id", "")) else kind)
    return {"canary_id":f"canary_{account}_{kind}","account_id":account,"canary_type":kind,"actual_post_type":actual_type,"permalink":fields["post_url"],"status":status,"reasons":reasons,**fields}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--apply",action="store_true");p.add_argument("--confirm-existing-evidence",action="store_true");p.add_argument("--retire-invalid",action="store_true");p.add_argument("--output",type=Path,required=True);a=p.parse_args()
 from config_loader import get_config
 from sheets_client import SheetsClient
 cfg=get_config(); client=SheetsClient(cfg["sheet_id"],cfg["sa_dict"],dry_run=not a.apply); data=live(client); inv=build_inventory(data)
 candidates={(str(c.get("account_id", "")), str(c.get("canary_type", ""))): c for c in inv["candidates"]}
 audit=[classify(candidates.get((account, kind), {"account_id":account,"canary_type":kind}), data["posted_results"]) for account, kind in REQUIRED_CANARIES]
 if a.apply and a.confirm_existing_evidence:
  for row in audit:
   if row["status"]!="EXISTING_CANARY_VALID": continue
   update_row(client,"posted_results","result_id",str(row["result_id"]),{"canary_id":row["canary_id"]})
  retired=[]
  if a.retire_invalid:
   for row in audit:
    if row["status"]!="EXISTING_CANARY_INVALID" or not str(row.get("result_id", "")):
     continue
    flags="excluded_from_activation=true; excluded_from_metrics_baseline=true; repost_prohibited=true"
    update_row(client,"posted_results","result_id",str(row["result_id"]),{"status":"INVALID_CONTENT_CANARY","manual_memo":flags})
    retired.append(str(row["result_id"]))
  after=records(client,"posted_results")
  valid_ids={x["canary_id"] for x in audit if x["status"]=="EXISTING_CANARY_VALID"}
  linked_ids={str(row.get("canary_id", "")) for row in after}
  missing_links=sorted(valid_ids-linked_ids)
  jobs=records(client,"metrics_collection_jobs")
  for job in build_metric_collection_jobs(after,jobs):
   if str(job.get("canary_id", "")) in valid_ids: append_row(client,"metrics_collection_jobs",job)
  data["posted_results"]=records(client,"posted_results"); data["metrics_collection_jobs"]=records(client,"metrics_collection_jobs")
  scheduled_ids={str(job.get("canary_id", "")) for job in data["metrics_collection_jobs"]}
  missing_schedule=sorted(valid_ids-scheduled_ids)
  mode="APPLIED" if not missing_links and not missing_schedule else "APPLY_READ_AFTER_WRITE_FAILED"
 else: mode="PLAN_ONLY"
 out={"status":mode,"sheets_status":"READ_OK","canaries":audit,"valid_count":sum(x["status"]=="EXISTING_CANARY_VALID" for x in audit),"invalid_count":sum(x["status"]=="EXISTING_CANARY_INVALID" for x in audit),"verify_required_count":sum(x["status"]=="VERIFY_REQUIRED" for x in audit),"retired_legacy_result_ids":retired if a.apply and a.confirm_existing_evidence else [],"apply_read_after_write":{"linked_canary_ids":sorted(valid_ids) if a.apply and a.confirm_existing_evidence else [],"missing_canary_links":missing_links if a.apply and a.confirm_existing_evidence else [],"missing_metric_schedules":missing_schedule if a.apply and a.confirm_existing_evidence else []},"would_post":False}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8");print(json.dumps({k:out[k] for k in ("status","valid_count","invalid_count","verify_required_count","would_post")},ensure_ascii=False))
 return 0
if __name__=="__main__":raise SystemExit(main())
