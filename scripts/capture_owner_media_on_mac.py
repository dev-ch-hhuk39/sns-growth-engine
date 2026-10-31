#!/usr/bin/env python3
"""Explicit Mac-only raw media capture; no provider, upload, queue or publisher."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from media.golden_evidence import validate_metadata_provenance, validate_registered_binding  # noqa: E402
from reference.source_registry import load_registry  # noqa: E402
from owner_media_permission_authority import request_hash, validate_request  # noqa: E402

MAX_MEDIA_BYTES = 300 * 1024**2
MAX_WORKSPACE_BYTES = 3 * 1024**3
MAX_JSON_BYTES = 2 * 1024**2
AUTHORITY_HOST = "fukuri-vps"  # Existing owner-approved SSH configuration.


def local_revision() -> str:
    def git(*args):
        result = subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=ROOT,
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise ValueError("local_revision_unverified")
        return result.stdout.strip()
    if git("rev-parse", "--show-toplevel") != str(ROOT) or git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("clean_local_checkout_required")
    revision = git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("local_revision_unverified")
    return revision


def mac_resources() -> tuple[int, int]:
    total = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                           timeout=10, check=True).stdout.strip()
    vm = subprocess.run(["/usr/bin/vm_stat"], capture_output=True, text=True, timeout=10, check=True).stdout
    return parse_mac_resources(total, vm)


def parse_mac_resources(total: str, vm: str) -> tuple[int, int]:
    page = re.search(r"page size of (\d+) bytes", vm)
    free = re.search(r"Pages free:\s+(\d+)", vm)
    inactive = re.search(r"Pages inactive:\s+(\d+)", vm)
    if not page or not free or not inactive or not total.isdigit() or int(page[1]) not in (4096, 16384):
        raise ValueError("mac_memory_unverified")
    # Match the available-memory formula in psutil's OS X implementation:
    # https://github.com/giampaolo/psutil/blob/master/psutil/arch/osx/mem.c
    available = int(page[1]) * (int(free[1]) + int(inactive[1]))
    if not 0 <= available <= int(total):
        raise ValueError("mac_memory_unverified")
    return int(total), available


def authority_request(host: str, request: dict, *, expected_local_revision: str) -> dict:
    if host != AUTHORITY_HOST:
        raise ValueError("approved_ssh_alias_required")
    validate_request(request)
    if local_revision() != expected_local_revision:
        raise ValueError("local_revision_changed")
    blob = subprocess.run(["git", "-c", "core.fsmonitor=false", "show",
                           expected_local_revision + ":scripts/owner_media_permission_authority.py"],
                          cwd=ROOT, capture_output=True, text=True, timeout=10, check=True)
    program = blob.stdout
    if not 1 <= len(program.encode()) <= 32768:
        raise ValueError("authority_program_unverified")
    interpreter = "/opt/github-runners/sns-growth-engine/.buffered-runtime/releases/" + request["revision"] + "/.venv/bin/python"
    command = "sudo -n -u snsrunner /usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8 " + shlex.quote(interpreter) + " -I -B -c "
    command += " ".join(shlex.quote(value) for value in (program, "--read-current", "--request-json", json.dumps(request)))
    result = subprocess.run(["ssh", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
                            capture_output=True, text=True, timeout=180)
    if result.returncode or len(result.stdout) > 16384:
        raise ValueError("live_permission_unverified")
    value = json.loads(result.stdout)
    if (value.get("status") != "ALLOW" or value.get("allowed") is not True
            or value.get("request_sha256") != request_hash(request) or value.get("revision") != request["revision"]
            or value.get("credentials_exported") is not False or value.get("production_writes") is not False
            or value.get("publish_authorized") is not False or value.get("operation") != "download"):
        raise ValueError("current_download_permission_required")
    binding = value.get("binding")
    if not isinstance(binding, dict) or any(binding.get(key) != request[key] for key in (
        "account_id", "source_id", "source_handle", "canonical_url")):
        raise ValueError("authority_source_binding_mismatch")
    verified = datetime.fromisoformat(value["verified_at"])
    age = (datetime.now(timezone.utc) - verified).total_seconds()
    if not -30 <= age <= 30:
        raise ValueError("fresh_permission_required")
    return value


def protected_workspace(path: Path, *, admission: bool = True) -> int:
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("private_workspace_required")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError("private_workspace_required")
    total, count = 0, 0
    for base, directories, files in os.walk(path, followlinks=False):
        if Path(base).relative_to(path).parts and len(Path(base).relative_to(path).parts) > 1:
            raise ValueError("workspace_structure_unverified")
        for name in directories + files:
            item = Path(base) / name
            state = item.lstat()
            count += 1
            if count > 512 or state.st_uid != os.geteuid() or stat.S_ISLNK(state.st_mode):
                raise ValueError("workspace_boundary_unverified")
            if stat.S_ISREG(state.st_mode):
                if state.st_nlink != 1 or state.st_mode & 0o022:
                    raise ValueError("workspace_file_unverified")
                total += state.st_size
            elif not stat.S_ISDIR(state.st_mode):
                raise ValueError("workspace_entry_unverified")
            elif stat.S_IMODE(state.st_mode) != 0o700:
                raise ValueError("private_workspace_directory_required")
    reserve = MAX_MEDIA_BYTES * 2 + MAX_JSON_BYTES * 2 + 65536 if admission else 0
    if total + reserve > MAX_WORKSPACE_BYTES or (admission and shutil.disk_usage(path).free < 2 * 1024**3):
        raise ValueError("workspace_capacity_unavailable")
    return total


def write_once(path: Path, value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > MAX_JSON_BYTES:
        raise ValueError("metadata_size_limit")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def stable_digest(path: Path) -> str:
    def identity(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or not 0 < info.st_size <= MAX_MEDIA_BYTES):
            raise ValueError("captured_file_unverified")
        return tuple(getattr(info, key) for key in ("st_dev", "st_ino", "st_mode", "st_uid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
    before = identity(path.lstat())
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    digest, total = hashlib.sha256(), 0
    with os.fdopen(descriptor, "rb") as stream:
        if identity(os.fstat(stream.fileno())) != before:
            raise ValueError("captured_file_changed")
        while chunk := stream.read(1024**2):
            total += len(chunk)
            if total > MAX_MEDIA_BYTES:
                raise ValueError("capture_size_limit")
            digest.update(chunk)
    if identity(path.lstat()) != before or total != before[5]:
        raise ValueError("captured_file_changed")
    return digest.hexdigest()


def capture(binding: dict, workspace: Path, host: str, revision: str, expected_local_revision: str) -> dict:
    if sys.platform != "darwin" or local_revision() != expected_local_revision:
        raise ValueError("verified_mac_checkout_required")
    total, available = mac_resources()
    if total < 4 * 1024**3 or available < 1536 * 1024**2:
        raise ValueError("mac_memory_floor_unmet")
    if version("yt-dlp") != "2026.7.4" or not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("pinned_media_tools_required")
    protected_workspace(workspace)
    lock = os.open(workspace / ".capture.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        state = os.fstat(lock)
        if (not stat.S_ISREG(state.st_mode) or state.st_uid != os.geteuid() or state.st_nlink != 1
                or stat.S_IMODE(state.st_mode) != 0o600):
            raise ValueError("capture_lock_unverified")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protected_workspace(workspace)
        request = {key: binding[key] for key in ("account_id", "source_id", "source_handle", "canonical_url")}
        request["revision"] = revision
        authority_request(host, request, expected_local_revision=expected_local_revision)
        job = workspace / binding["platform"]
        job.mkdir(mode=0o700, exist_ok=True)
        protected_workspace(workspace)
        attempt = request_hash(request)
        native = binding["external_post_id"]
        basename = binding["account_id"] + "_" + binding["source_id"] + "_" + native
        if any(job.glob(basename + ".*")):
            raise ValueError("existing_media_requires_reconciliation")
        # The manifest's X/YouTube verifiers consume one flat directory per
        # platform. Separate durable request records prevent duplicate jobs.
        write_once(job / (attempt + ".request.json"), {**request, "local_revision": expected_local_revision, "state": "PREPARED"})
        path = job / (basename + ".mp4")
        calls = 0

        def match_filter(info, *, incomplete=False):
            nonlocal calls
            if incomplete:
                return None
            if info.get("is_live") is True or info.get("live_status") in {"is_live", "post_live"}:
                raise ValueError("recorded_individual_media_required")
            if validate_metadata_provenance(binding, info)["status"] != "PASS":
                raise ValueError("extracted_post_author_unverified")
            calls += 1
            if calls > 8:
                raise ValueError("metadata_attempt_bound")
            authority_request(host, request, expected_local_revision=expected_local_revision)  # Before download.
            return None

        def byte_guard(status):
            if int(status.get("downloaded_bytes") or 0) > MAX_MEDIA_BYTES:
                raise ValueError("capture_size_limit")
            total_bytes = 0
            for item in job.glob(basename + ".*"):
                state = item.lstat()
                if not stat.S_ISREG(state.st_mode) or state.st_uid != os.geteuid() or state.st_nlink != 1:
                    raise ValueError("capture_file_unverified")
                total_bytes += state.st_size
            if total_bytes > MAX_MEDIA_BYTES:
                raise ValueError("capture_size_limit")
            protected_workspace(workspace, admission=False)

        def processing_guard(status):
            if status.get("status") == "started":
                byte_guard({})
            else:
                protected_workspace(workspace, admission=False)

        class QuietLogger:
            def debug(self, _message): pass
            def warning(self, _message): pass
            def error(self, _message): pass

        # The pinned library's plugin loader supports this switch. Anonymous
        # source acquisition must not load browser/cookie/PO-token plugins.
        os.environ["YTDLP_NO_PLUGINS"] = "1"
        from yt_dlp import YoutubeDL
        options = {"outtmpl": str(job / (basename + ".%(ext)s")), "noplaylist": True,
            "quiet": True, "noprogress": True, "no_warnings": True, "logger": QuietLogger(), "cachedir": False,
            "usenetrc": False, "cookiefile": None, "cookiesfrombrowser": None,
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "merge_output_format": "mp4", "overwrites": False, "continuedl": False,
            "retries": 0, "fragment_retries": 0, "extractor_retries": 0, "socket_timeout": 20,
            "max_filesize": MAX_MEDIA_BYTES, "match_filter": match_filter,
            "progress_hooks": [byte_guard], "postprocessor_hooks": [processing_guard]}
        with YoutubeDL(options) as downloader:
            metadata = downloader.extract_info(binding["canonical_url"], download=True)
            metadata = downloader.sanitize_info(metadata, remove_private_keys=True)
        if calls == 0 or validate_metadata_provenance(binding, metadata)["status"] != "PASS":
            raise ValueError("download_binding_unverified")
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                or not 0 < info.st_size <= MAX_MEDIA_BYTES):
            raise ValueError("download_bytes_unverified")
        path.chmod(0o600)
        from generation.video_clip_materializer import probe_media_streams
        probe = probe_media_streams(path, timeout_seconds=30)
        duration = float(probe.get("duration_seconds") or 0)
        if (int(probe.get("video_stream_count") or 0) < 1 or int(probe.get("audio_stream_count") or 0) < 1
                or int(probe.get("width") or 0) <= 0 or int(probe.get("height") or 0) <= 0
                or not math.isfinite(duration) or duration <= 0):
            raise ValueError("video_audio_required")
        authority_request(host, request, expected_local_revision=expected_local_revision)  # Recheck revoke.
        digest = stable_digest(path)
        if local_revision() != expected_local_revision:
            raise ValueError("local_revision_changed")
        write_once(path.with_suffix(".info.json"), metadata)
        protected_workspace(workspace, admission=False)
        result = {"status": "LOCAL_RAW_ARTIFACT_CAPTURED", "account_id": binding["account_id"],
            "platform": binding["platform"], "source_id": binding["source_id"], "content_hash": digest,
            "content_understanding": "NOT_RUN", "overall_goal_acceptance": False,
            "production_writes": False, "provider_calls": 0, "publish_authorized": False,
            "queue_created": False, "credentials_exported": False}
        write_once(job / (attempt + ".result.json"), result)
        return result
    finally:
        os.close(lock)


def isolated_capture(arguments: list[str]) -> dict:
    """Provider credentials never enter the Mac download process."""
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "en_US.UTF-8", "YTDLP_NO_PLUGINS": "1"}
    if os.environ.get("SSH_AUTH_SOCK"):
        environment["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]
    process = subprocess.Popen([sys.executable, "-I", "-B", str(Path(__file__).resolve()),
                                *arguments, "--worker"], env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        output, _errors = process.communicate(timeout=900)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
        raise ValueError("capture_deadline_exceeded") from None
    if process.returncode or len(output) > 16384:
        raise ValueError("capture_worker_unverified")
    result = json.loads(output)
    allowed_keys = {"status", "account_id", "platform", "source_id", "content_hash", "content_understanding",
                    "production_writes", "publish_authorized", "provider_calls", "credentials_exported",
                    "queue_created", "overall_goal_acceptance"}
    if (not isinstance(result, dict) or set(result) != allowed_keys
            or result.get("status") != "LOCAL_RAW_ARTIFACT_CAPTURED"
            or result.get("account_id") not in {"night_scout", "liver_manager"}
            or result.get("platform") not in {"x", "youtube"}
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", str(result.get("source_id", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(result.get("content_hash", "")))
            or result.get("content_understanding") != "NOT_RUN"
            or type(result.get("provider_calls")) is not int
            or result.get("production_writes") is not False
            or result.get("publish_authorized") is not False or result.get("provider_calls") != 0
            or result.get("credentials_exported") is not False or result.get("queue_created") is not False
            or result.get("overall_goal_acceptance") is not False):
        raise ValueError("capture_result_unverified")
    return result


def scrub_worker_environment() -> None:
    allowed = {"PATH", "LANG", "LC_CTYPE", "SSH_AUTH_SOCK", "YTDLP_NO_PLUGINS"}
    for name in list(os.environ):
        if name not in allowed:
            del os.environ[name]
    os.environ["YTDLP_NO_PLUGINS"] = "1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=("night_scout", "liver_manager"))
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-download", action="store_true")
    parser.add_argument("--authority-host")
    parser.add_argument("--expected-runtime-revision")
    parser.add_argument("--expected-local-revision")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    registry = load_registry(preserve_duplicates=True)
    sources = [row for row in registry if row.get("source_id") == args.source_id]
    item = {"account_id": args.account_id, "source_id": args.source_id, "url": args.url,
            "source_handle": sources[0].get("source_handle") if len(sources) == 1 else ""}
    decision = validate_registered_binding(item, registry)
    if decision["status"] != "PASS":
        print(json.dumps({"status": "BLOCKED", "reasons": ["registered_owner_source_required"]}))
        return 2
    if not args.apply:
        if args.confirm_download:
            parser.error("confirmation requires --apply")
        print(json.dumps({"status": "PLAN_ONLY", "account_id": args.account_id,
            "platform": decision["binding"]["platform"], "would_connect": False, "would_download": False,
            "would_write_production": False, "would_post": False, "credentials_exported": False}))
        return 0
    if (not args.confirm_download or not args.workspace or not args.authority_host
            or not re.fullmatch(r"[0-9a-f]{40}", args.expected_runtime_revision or "")
            or not re.fullmatch(r"[0-9a-f]{40}", args.expected_local_revision or "")):
        parser.error("apply requires confirmation, private workspace, authority and both exact revisions")
    try:
        if args.worker:
            scrub_worker_environment()
            result = capture(decision["binding"], args.workspace, args.authority_host,
                             args.expected_runtime_revision, args.expected_local_revision)
        else:
            result = isolated_capture(sys.argv[1:])
    except Exception:
        print(json.dumps({"status": "BLOCKED", "reasons": ["capture_unverified_no_automatic_retry"],
                          "production_writes": False, "publish_authorized": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
