#!/usr/bin/env python3
from production_novelty import evaluate_candidate_novelty

text = "配信で初見が参加しやすい空気を作ると、コメントの入口が増えやすい。"
assert evaluate_candidate_novelty(account_id="liver_manager", public_post_text=text, recent_posts=[], pending_queue=[])["status"] == "PASS"
assert evaluate_candidate_novelty(account_id="liver_manager", public_post_text=text, recent_posts=[{"account_id": "liver_manager", "posted_text": text}], pending_queue=[])["status"] == "BLOCKED"
assert evaluate_candidate_novelty(account_id="liver_manager", public_post_text=text, recent_posts=[], pending_queue=[{"account_id": "liver_manager", "public_post_text": text}])["status"] == "BLOCKED"
print("PASS test_production_novelty_contract.py")
