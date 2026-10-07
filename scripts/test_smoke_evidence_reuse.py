#!/usr/bin/env python3
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1] / 'src')]
import build_media_first_review_pack as preview
from run_content_quality_v2_vision_smoke import SmokeGeminiClient, current_model_scoped_vision_fallback_allowed

class EvidenceReuseTests(unittest.TestCase):
    def test_exact_binding_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / 'f.jpg'; frame.write_bytes(b'frame')
            digest = hashlib.sha256(b'media').hexdigest(); fh = hashlib.sha256(b'frame').hexdigest()
            row = {'account_id':'night_scout','media_asset_id':'asset','preview_url':'https://res.cloudinary.com/fixture'}
            vision = {'provider':'gemini','model':'gemini-3.5-flash','status':'PASS','response_schema_status':'PASS',
                      'frame_hashes':[fh], 'visual_facts':[{'id':'VF1','type':'visible_text','text':'fixture'}]}
            packet = {'account_id':'night_scout','media_asset_id':'asset','content_hash':digest,
                      'frame_hashes':[fh],'vision':vision,'origin_run_id':'fixture',
                      'evidence_sha256':hashlib.sha256(json.dumps(vision,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
            response = Mock(status_code=200);response.iter_content.return_value=[b'media']
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            for field in (None, 'account_id','media_asset_id','content_hash','frame_hashes','evidence_sha256','visual_facts'):
                saved=copy.deepcopy(packet)
                if field=='visual_facts': saved['vision']['visual_facts'][0]['text']='changed'
                elif field: saved[field]='mismatch'
                with patch.object(preview.requests,'get',return_value=response), \
                     patch.object(preview.subprocess,'run',return_value=Mock(stdout='{"format":{"duration":1},"streams":[{"codec_type":"video"}]}')), \
                     patch.object(preview,'representative_frames',return_value=[(0,frame)]), \
                     patch.object(preview,'vision_summary',return_value={'status':'UNAVAILABLE'}) as call:
                    result=preview.inspect_preview(row,Path(tmp),smoke_vision_evidence=saved)
                    self.assertEqual(call.call_count,0 if field is None else 1,field)
                    if field is None:
                        self.assertEqual(result['vision']['attempt_count'],0)
                        self.assertEqual(result['vision']['evidence_reused_from_run'],'fixture')

    def test_vision_model_override_is_smoke_scoped_and_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "f.jpg"
            frame.write_bytes(b"frame")
            row = {"account_id":"liver_manager","media_asset_id":"asset","preview_url":"https://res.cloudinary.com/fixture"}
            response = Mock(status_code=200)
            response.iter_content.return_value=[b"media"]
            response.__enter__=Mock(return_value=response)
            response.__exit__=Mock(return_value=False)
            seen = []

            def fake_vision(*args, **kwargs):
                model = os.environ.get("GEMINI_VISION_MODEL", "")
                seen.append(model)
                return {"provider":"gemini","model":model,"status":"PASS","response_schema_status":"PASS",
                        "visual_summary":"fixture summary","visible_action":"","key_moment":"fixture moment",
                        "visual_facts":[{"id":"VF1","type":"visible_text","text":"fixture text"}],
                        "http_status":200,"frame_hashes":[hashlib.sha256(b"frame").hexdigest()]}

            with patch.dict(os.environ, {"GEMINI_VISION_MODEL":"gemini-3.5-flash"}, clear=False),                  patch.object(preview.requests, "get", return_value=response),                  patch.object(preview.subprocess, "run", return_value=Mock(stdout='{"format":{"duration":1},"streams":[{"codec_type":"video"}]}')),                  patch.object(preview, "representative_frames", return_value=[(0, frame)]),                  patch.object(preview, "vision_summary", side_effect=fake_vision):
                result = preview.inspect_preview(row, Path(tmp), vision_model_override="gemini-3.1-flash-lite")
                self.assertEqual(os.environ["GEMINI_VISION_MODEL"], "gemini-3.5-flash")

            self.assertEqual(seen, ["gemini-3.1-flash-lite"])
            self.assertEqual(result["vision"]["model"], "gemini-3.1-flash-lite")
            self.assertEqual(result["vision"]["requested_model"], "gemini-3.5-flash")
            self.assertTrue(result["vision"]["fallback_used"])

    def test_current_run_model_scoped_quota_allows_smoke_vision_fallback(self):
        vision = {
            "http_status": 429,
            "quota_violations": [{
                "quota_model": "gemini-3.5-flash",
                "quota_id": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                "rate_limit_class": "DAILY_QUOTA_EXHAUSTED",
            }],
        }
        self.assertTrue(current_model_scoped_vision_fallback_allowed(vision, "gemini-3.5-flash"))
        self.assertFalse(current_model_scoped_vision_fallback_allowed(vision, "gemini-3.1-flash-lite"))
        vision["quota_violations"][0]["quota_id"] = "GenerateRequestsPerDayPerProject"
        self.assertFalse(current_model_scoped_vision_fallback_allowed(vision, "gemini-3.5-flash"))

    def test_fallback_only_on_active_model_scoped_evidence(self):
        client=SmokeGeminiClient(api_key='fixture',reserve_request=Mock())
        client.quota_basis={'observed_at':datetime.now(timezone.utc).isoformat(),'retry_delay_seconds':60,
                            'quota_violations':[{'quota_model':'gemini-3.5-flash','quota_id':'GenerateRequestsPerDayPerProjectPerModel-FreeTier','rate_limit_class':'DAILY_QUOTA_EXHAUSTED'}]}
        self.assertTrue(client.fallback_allowed('gemini-3.5-flash'))
        self.assertFalse(client.fallback_allowed('gemini-3.1-flash-lite'))
        client.quota_basis['quota_violations'][0]['quota_id']='GenerateRequestsPerDayPerProject'
        self.assertFalse(client.fallback_allowed('gemini-3.5-flash'))
        client.quota_basis['quota_violations'][0]['quota_id']='GenerateRequestsPerDayPerProjectPerModel-FreeTier'
        client.quota_basis['observed_at']='2000-01-01T00:00:00Z'
        self.assertFalse(client.fallback_allowed('gemini-3.5-flash'))

if __name__=='__main__': unittest.main()
