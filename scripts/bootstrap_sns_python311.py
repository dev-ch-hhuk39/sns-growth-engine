#!/usr/bin/env python3
"""Create a self-contained-per-release Python 3.11 venv from the owned toolcache.

The dedicated SNS runner's setup-python binary has a hosted-runner RUNPATH
which is invalid on Xserver. Never modify the shared system Python or the
original setup-python installation. Patch COPIES of the venv executables only.

This entrypoint accepts an exact SNS-owned, transient immutable-release stage.
There are no delete, activate, post, backup or cross-application operations.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

TOOLCACHE_PREFIX = Path(
    "/opt/github-runners/sns-growth-engine/_work/_tool/Python/3.11.17/x64"
)
RELEASES = Path(
    "/opt/github-runners/sns-growth-engine/.buffered-runtime/releases"
)
VERSION = "3.11.17"
PATCHELF_PACKAGE = "patchelf==0.17.2.4"
PATCHELF_FILENAME = (
    "patchelf-0.17.2.4-py3-none-manylinux1_x86_64."
    "manylinux_2_5_x86_64.musllinux_1_1_x86_64.whl"
)
PATCHELF_SHA256 = (
    "d9b35ebfada70c02679ad036407d9724ffe1255122ba4ac5e4be5868618a5689"
)
STAGE = re.compile(r"\.stage-[0-9a-f]{40}\.[A-Za-z0-9]{6}\Z")


class BootstrapBlocked(RuntimeError):
    """Sanitized reason code, never a source of secrets."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise BootstrapBlocked(reason)


def ordinary_owned_dir(path: Path, uid: int) -> None:
    meta = path.lstat()
    require(stat.S_ISDIR(meta.st_mode) and not path.is_symlink(),
            "SNS_PY311_DIRECTORY_UNSAFE")
    require(meta.st_uid == uid, "SNS_PY311_OWNER_MISMATCH")


def production_preflight(stage: Path) -> None:
    require(sys.platform == "linux" and os.uname().machine == "x86_64",
            "SNS_PY311_LINUX_X64_ONLY")
    uid = os.getuid()
    require(uid != 0, "SNS_PY311_REFUSE_ROOT")
    require(bool(STAGE.fullmatch(stage.name)), "SNS_PY311_STAGE_NAME_UNVERIFIED")
    require(stage.parent == RELEASES, "SNS_PY311_STAGE_OUT_OF_SCOPE")
    require(stage.resolve(strict=True) == stage,
            "SNS_PY311_STAGE_ALIAS_FORBIDDEN")
    ordinary_owned_dir(stage, uid)
    ordinary_owned_dir(RELEASES, uid)
    ordinary_owned_dir(TOOLCACHE_PREFIX, uid)
    ordinary_owned_dir(TOOLCACHE_PREFIX / "lib", uid)
    ordinary_owned_dir(TOOLCACHE_PREFIX / "bin", uid)
    required = [
        TOOLCACHE_PREFIX / "bin" / "python3.11",
        TOOLCACHE_PREFIX / "lib" / "libpython3.11.so.1.0",
    ]
    for path in required:
        meta = path.lstat()
        require(stat.S_ISREG(meta.st_mode) and not path.is_symlink(),
                "SNS_PY311_INTERPRETER_UNSAFE")
        require(meta.st_uid == uid, "SNS_PY311_INTERPRETER_OWNER_MISMATCH")
    require(not (stage / ".venv").exists()
            and not (stage / ".venv").is_symlink(),
            "SNS_PY311_STAGE_VENV_ALREADY_EXISTS")


def safe_call(args: list[str], *, env: dict[str, str] | None = None,
              timeout: int = 90, reason: str) -> str:
    try:
        result = subprocess.run(
            args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BootstrapBlocked(reason) from None
    require(result.returncode == 0, reason)
    return result.stdout


def obtain_pinned_patchelf(scratch: Path, env: dict[str, str]) -> Path:
    py = str(TOOLCACHE_PREFIX / "bin" / "python3.11")
    safe_call(
        [py, "-m", "pip", "download", "--quiet", "--only-binary=:all:",
         "--no-deps", "--dest", str(scratch), PATCHELF_PACKAGE],
        env=env, timeout=90, reason="SNS_PY311_PATCH_TOOL_FETCH_FAILED",
    )
    wheels = list(scratch.glob("*.whl"))
    require(len(wheels) == 1 and wheels[0].name == PATCHELF_FILENAME,
            "SNS_PY311_PATCH_TOOL_WHEEL_UNEXPECTED")
    digest = hashlib.sha256(wheels[0].read_bytes()).hexdigest()
    require(digest == PATCHELF_SHA256,
            "SNS_PY311_PATCH_TOOL_HASH_MISMATCH")
    try:
        with zipfile.ZipFile(wheels[0]) as archive:
            matches = [
                name for name in archive.namelist()
                if name.endswith(".data/scripts/patchelf")
            ]
            require(len(matches) == 1,
                    "SNS_PY311_PATCH_TOOL_CONTENT_UNEXPECTED")
            content = archive.read(matches[0])
    except (OSError, zipfile.BadZipFile):
        raise BootstrapBlocked("SNS_PY311_PATCH_TOOL_READ_FAILED") from None
    require(100_000 < len(content) < 5_000_000 and content[:4] == b"\x7fELF",
            "SNS_PY311_PATCH_TOOL_BINARY_INVALID")
    output = scratch / "patchelf"
    output.write_bytes(content)
    output.chmod(0o700)
    return output


def patch_venv_executables(venv: Path, patchelf: Path) -> None:
    require(venv.is_dir() and not venv.is_symlink(), "SNS_PY311_VENV_UNSAFE")
    for name in ("python", "python3", "python3.11"):
        binary = venv / "bin" / name
        meta = binary.lstat()
        require(stat.S_ISREG(meta.st_mode) and not binary.is_symlink()
                and meta.st_uid == os.getuid(),
                "SNS_PY311_VENV_BINARY_UNSAFE")
        safe_call(
            [str(patchelf), "--set-rpath",
             str(TOOLCACHE_PREFIX / "lib"), str(binary)],
            timeout=20, reason="SNS_PY311_VENV_RPATH_PATCH_FAILED",
        )
        actual = safe_call(
            [str(patchelf), "--print-rpath", str(binary)],
            timeout=10, reason="SNS_PY311_VENV_RPATH_UNVERIFIABLE",
        )
        require(actual.strip() == str(TOOLCACHE_PREFIX / "lib"),
                "SNS_PY311_VENV_RPATH_WRONG")


def bootstrap(stage: Path) -> None:
    production_preflight(stage)
    original_env = dict(os.environ)
    original_env["LD_LIBRARY_PATH"] = (
        str(TOOLCACHE_PREFIX / "lib")
        + (":" + original_env["LD_LIBRARY_PATH"]
           if original_env.get("LD_LIBRARY_PATH") else "")
    )
    original_env["PIP_NO_CACHE_DIR"] = "1"
    original_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    py = str(TOOLCACHE_PREFIX / "bin" / "python3.11")
    safe_call(
        [py, "-c", "import sys; assert sys.version.split()[0] == '3.11.17'"],
        env=original_env, timeout=15,
        reason="SNS_PY311_INTERPRETER_VERSION_UNEXPECTED",
    )
    with tempfile.TemporaryDirectory(
        prefix=".sns-python-bootstrap-", dir=str(stage)
    ) as temp:
        patchelf = obtain_pinned_patchelf(Path(temp), original_env)
        venv = stage / ".venv"
        safe_call(
            [py, "-m", "venv", "--copies", str(venv)], env=original_env,
            timeout=65, reason="SNS_PY311_VENV_CREATION_FAILED",
        )
        patch_venv_executables(venv, patchelf)
        code = (
            "import sys,ssl,sqlite3;"
            "assert sys.version_info[:3] == (3,11,17);"
            "assert sys.prefix == " + repr(str(venv)) + ";"
            "assert sys.base_prefix != sys.prefix;"
            "assert ssl.OPENSSL_VERSION;"
        )
        # Explicitly NOT passing LD_LIBRARY_PATH: each copied venv binary must
        # start by itself during unattended cron/rollback, not just in CI.
        for name in ("python", "python3", "python3.11"):
            safe_call(
                [str(venv / "bin" / name), "-c", code],
                env={key: value for key, value in original_env.items()
                     if key != "LD_LIBRARY_PATH"},
                timeout=20, reason="SNS_PY311_VENV_STANDALONE_SMOKE_FAILED",
            )
    print("SNS_OWNED_PYTHON_311_VENV=PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    args = parser.parse_args()
    try:
        bootstrap(args.stage)
    except (BootstrapBlocked, OSError, ValueError) as error:
        reason = str(error)
        if not reason.startswith("SNS_PY311_"):
            reason = "SNS_PY311_UNVERIFIED_FAILURE"
        print(reason, file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
