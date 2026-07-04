#!/usr/bin/env python3
from media_growth_schemas import score_clip_candidate

def main() -> int:
    scores = score_clip_candidate({"rights_status": "approved_creator_clip"}, has_transcript=True)
    ok = scores["clip_score"] > 0 and scores["rights_score"] == 20 and scores["risk_score"] <= 10
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate scoring")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
