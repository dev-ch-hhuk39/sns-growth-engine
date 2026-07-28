#!/usr/bin/env python3
"""Exercise the real X adapter shape with a local tweepy-compatible fake."""
from __future__ import annotations
import importlib.util, os, sys, types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; path=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("collect", path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
class Obj:
    def __init__(self, **kwargs): self.__dict__.update(kwargs)
class Client:
    def __init__(self, **kwargs): pass
    def get_user(self, **kwargs): return Obj(data=Obj(id="u1"))
    def get_users_tweets(self, *args, **kwargs): return Obj(data=[Obj(id="123", text="reference text", created_at="2026-07-29T00:00:00+00:00", attachments={"media_keys":["m1","m2"]})], includes={"media":[Obj(media_key="m1",url="https://cdn.example/1.jpg"),Obj(media_key="m2",preview_image_url="https://cdn.example/2.jpg")]})
old_spec=mod.importlib.util.find_spec; old_env=os.environ.get("X_READ_ONLY_BEARER_TOKEN"); old_module=sys.modules.get("tweepy")
mod.importlib.util.find_spec=lambda name: object() if name=="tweepy" else old_spec(name); os.environ["X_READ_ONLY_BEARER_TOKEN"]="present"; sys.modules["tweepy"]=types.SimpleNamespace(Client=Client)
try:
    result=mod.fetch_x_account_posts({"x_read_only":True,"source_handle":"@meg_lsm"},limit=10)
finally:
    mod.importlib.util.find_spec=old_spec
    if old_env is None: os.environ.pop("X_READ_ONLY_BEARER_TOKEN",None)
    else: os.environ["X_READ_ONLY_BEARER_TOKEN"]=old_env
    if old_module is None: sys.modules.pop("tweepy",None)
    else: sys.modules["tweepy"]=old_module
row=result["rows"][0]
checks=[("fetched",result["status"]=="FETCHED"), ("individual status url",row["post_url"]=="https://x.com/meg_lsm/status/123"), ("external id",row["external_post_id"]=="123"), ("media order retained",row["media_urls"]==["https://cdn.example/1.jpg","https://cdn.example/2.jpg"])]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
