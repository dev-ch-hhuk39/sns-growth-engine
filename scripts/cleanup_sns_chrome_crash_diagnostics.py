#!/usr/bin/env python3
"""SNS-only old Chrome crash telemetry cleanup. No runtime/model/backup access."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
import re
from pathlib import Path
import pwd
import stat
import time

BASE = Path("/var/lib/sns-growth-engine/.config/google-chrome/Crash Reports")
TARGET = BASE / "completed"
LOCK = Path("/run/lock/chadult-production-deploy.lock")
MAX_COUNT = 3000
NAME = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.(?:dmp|meta)\Z")
MAX_BYTES = 100_000_000
MIN_AGE = 14 * 86400

class Unsafe(RuntimeError):
    pass

def require(value, why):
    if not value:
        raise Unsafe(why)

def own_dir(path, uid):
    entry=path.lstat()
    require(stat.S_ISDIR(entry.st_mode) and not path.is_symlink() and entry.st_uid==uid,
            "UNTRUSTED_SNS_CRASH_DIR")

def candidate_files(target, uid, now):
    own_dir(target,uid)
    files=[]
    total=0
    for path in target.iterdir():
        st=path.lstat()
        require(stat.S_ISREG(st.st_mode) and not path.is_symlink()
                and st.st_uid==uid and st.st_nlink==1, "UNTRUSTED_CHILD_FILE")
        require(path.suffix in {".dmp",".meta"} and NAME.fullmatch(path.name),
                "UNKNOWN_CHILD_EXTENSION")
        if now-st.st_mtime < MIN_AGE:
            continue
        require(st.st_size<=250_000,"LARGE_CRASH_FILE_UNEXPECTED")
        files.append((path,st.st_ino,st.st_mtime_ns,st.st_size))
        total+=st.st_size
    require(len(files)<=MAX_COUNT and total<=MAX_BYTES,"CANDIDATE_SCOPE_TOO_LARGE")
    return files,total

def candidates(uid, now):
    require(os.getuid()==uid, "WRONG_USER")
    for path in (Path("/var/lib/sns-growth-engine"),
                 Path("/var/lib/sns-growth-engine/.config"),
                 Path("/var/lib/sns-growth-engine/.config/google-chrome"),
                 BASE, TARGET):
        own_dir(path,uid)
    return candidate_files(TARGET,uid,now)

def check_no_live_chrome(uid):
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name)==os.getpid():
            continue
        try:
            st=(proc/"status").read_text(errors="replace")
            userline=next((line for line in st.splitlines() if line.startswith("Uid:")),None)
            if not userline:
                continue
            parts=userline.split()
            if int(parts[1])!=uid:
                continue
            comm=(proc/"comm").read_text(errors="replace").strip().lower()
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError):
            raise Unsafe("SNS_PROCESS_AUDIT_UNAVAILABLE") from None
        # Check the executable's process name, not a CI shell command line
        # containing this script name (which includes the word "chrome").
        if "chrome" in comm or "chromium" in comm:
            raise Unsafe("SNS_CHROME_ACTIVE")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    uid=pwd.getpwnam("snsrunner").pw_uid
    try:
        require(LOCK.is_file() and not LOCK.is_symlink(),"SHARED_LOCK_MISSING")
        with LOCK.open("rb") as f:
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            check_no_live_chrome(uid)
            files,total=candidates(uid,time.time())
            before=os.statvfs(str(TARGET))
            free_before=before.f_bavail*before.f_frsize
            if args.apply:
                for path,ino,mtime,size in files:
                    now=path.lstat()
                    require(now.st_ino==ino and now.st_mtime_ns==mtime
                            and now.st_size==size and stat.S_ISREG(now.st_mode)
                            and now.st_nlink==1 and now.st_uid==uid,
                            "CANDIDATE_CHANGED_DURING_CLEANUP")
                    path.unlink()
            after=os.statvfs(str(TARGET))
            free_after=after.f_bavail*after.f_frsize
        print(json.dumps({"status":"PASS","mode":"APPLY" if args.apply else "DRY_RUN",
                          "scope":"sns_only_completed_old_chrome_crash_reports",
                          "age_days_min":14,"files_removed":len(files) if args.apply else 0,
                          "planned_bytes":total,
                          "free_bytes_delta":max(0,free_after-free_before),
                          "other_apps_touched":False,"production_release_touched":False,
                          "r2_backup_touched":False},sort_keys=True))
        return 0
    except (Unsafe,OSError,BlockingIOError) as exc:
        print(json.dumps({"status":"BLOCKED","category":type(exc).__name__,
                          "other_apps_touched":False},sort_keys=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
