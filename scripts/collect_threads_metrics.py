#!/usr/bin/env python3
"""Collect Threads metrics safely.

Default mode is PLAN_ONLY. This collector never fabricates unknown values:
unknown metrics stay null, confirmed zero stays 0. Real writes require
--apply --confirm-metrics.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from publishers.threads_credentials import resolve_credentials  # noqa: E402

METRIC_KEYS = (
    "views",
    "likes",
    "comments",
    "reposts",
    "quotes",
    "profile_clicks",
    "follows",
    "line_adds",
)

PDCA_REQUIRED_METRIC_KEYS = (
    "views",
    "likes",
    "comments",
)

THREADS_POST_INSIGHT_METRICS = (
    "views",
    "likes",
    "replies",
    "reposts",
    "quotes",
)

ALLOWED_ACCOUNTS = {
    "night_scout",
    "liver_manager",
    "beauty_account",
}

PUBLIC_TIMEOUT_SECONDS = 15
THREADS_API_BASE = (
    "https://graph.threads.net/v1.0"
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_metric(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    return int(str(value).strip())


def _fetch_public_html(url: str) -> tuple[str, str]:
    if not url:
        return "", "post_url_missing"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sns-growth-engine/2.0; +dry-run)"})
    try:
        with urllib.request.urlopen(req, timeout=PUBLIC_TIMEOUT_SECONDS) as res:
            return res.read(2_000_000).decode("utf-8", errors="replace"), ""
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


def _first_int(patterns: list[str], text: str) -> int | None:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return int(str(m.group(1)).replace(",", ""))
    return None


def dependency_status() -> dict[str, str]:
    return {
        "playwright": (
            "installed"
            if importlib.util.find_spec(
                "playwright"
            )
            else "not_installed"
        ),
        "public_html_og": "wired",
        "threads_insights_api": "wired",
    }


def collect_public_threads_metrics(row: dict[str, Any], source: str) -> tuple[dict[str, int | None], str, str]:
    """Best-effort public page parser.

    Threads public pages often hide exact metrics from logged-out HTML. When
    values are absent, keep them as None and return UNAVAILABLE/low confidence.
    """
    html_text, error = _fetch_public_html(str(row.get("post_url", "")))
    metrics = {k: None for k in METRIC_KEYS}
    if error:
        return metrics, "none", error
    text = html.unescape(html_text)
    metrics["likes"] = _first_int([r'"like_count"\s*:\s*(\d+)', r'(\d[\d,]*)\s+likes?'], text)
    metrics["comments"] = _first_int([r'"reply_count"\s*:\s*(\d+)', r'(\d[\d,]*)\s+repl(?:y|ies)'], text)
    metrics["reposts"] = _first_int([r'"reshare_count"\s*:\s*(\d+)', r'(\d[\d,]*)\s+reposts?'], text)
    if any(v is not None for v in metrics.values()):
        return metrics, "low", "public_html_partial"
    return metrics, "none", "public_html_no_metrics"



def _empty_metrics() -> dict[str, int | None]:
    return {
        key: None
        for key in METRIC_KEYS
    }


def _metric_value(
    insight: dict[str, Any],
) -> int | None:
    candidates: list[Any] = []

    total = insight.get("total_value")

    if isinstance(total, dict):
        candidates.append(
            total.get("value")
        )

    values = insight.get("values")

    if (
        isinstance(values, list)
        and values
        and isinstance(
            values[-1],
            dict,
        )
    ):
        candidates.append(
            values[-1].get("value")
        )

    candidates.append(
        insight.get("value")
    )

    for value in candidates:
        if value is None or value == "":
            continue

        try:
            parsed = int(
                float(value)
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        if parsed >= 0:
            return parsed

    return None


def parse_threads_insights_payload(
    payload: dict[str, Any],
) -> dict[str, int | None]:
    metrics = _empty_metrics()

    for insight in payload.get(
        "data",
        [],
    ):
        if not isinstance(
            insight,
            dict,
        ):
            continue

        name = str(
            insight.get("name", "")
        ).strip().lower()

        destination = (
            "comments"
            if name == "replies"
            else name
        )

        if destination not in metrics:
            continue

        value = _metric_value(
            insight
        )

        if value is not None:
            metrics[destination] = (
                value
            )

    return metrics


def collect_api_threads_metrics(
    row: dict[str, Any],
    access_token: str,
) -> tuple[
    dict[str, int | None],
    str,
    str,
]:
    """Read official post insights without exposing credentials."""

    metrics = _empty_metrics()

    post_id = str(
        row.get(
            "external_post_id",
            "",
        )
    ).strip()

    if not post_id:
        return (
            metrics,
            "none",
            "external_post_id_missing",
        )

    if not access_token:
        return (
            metrics,
            "none",
            "threads_access_token_missing",
        )

    query = urllib.parse.urlencode(
        {
            "metric": ",".join(
                THREADS_POST_INSIGHT_METRICS
            )
        }
    )

    url = (
        f"{THREADS_API_BASE}/"
        f"{urllib.parse.quote(post_id, safe='')}"
        f"/insights?{query}"
    )

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Accept": "application/json",
            "User-Agent": (
                "sns-growth-engine/"
                "threads-insights"
            ),
        },
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=PUBLIC_TIMEOUT_SECONDS,
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )
    except urllib.error.HTTPError as exc:
        return (
            metrics,
            "none",
            f"HTTPError:{exc.code}",
        )
    except urllib.error.URLError as exc:
        return (
            metrics,
            "none",
            (
                "URLError:"
                f"{type(exc.reason).__name__}"
            ),
        )
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        return (
            metrics,
            "none",
            type(exc).__name__,
        )
    except Exception as exc:
        return (
            metrics,
            "none",
            type(exc).__name__,
        )

    metrics = parse_threads_insights_payload(
        payload
    )

    required_known = all(
        metrics[key] is not None
        for key in PDCA_REQUIRED_METRIC_KEYS
    )

    if required_known:
        return metrics, "high", ""

    if any(
        value is not None
        for value in metrics.values()
    ):
        return (
            metrics,
            "medium",
            "threads_api_partial",
        )

    return (
        metrics,
        "none",
        "threads_api_no_metrics",
    )


def collect_playwright_threads_metrics(row: dict[str, Any], storage_state: str = "") -> tuple[dict[str, int | None], str, str]:
    """Best-effort Playwright page adapter.

    This never prints cookies/tokens. If browser binaries or login state are
    unavailable, the caller gets UNAVAILABLE rather than fabricated zeroes.
    """
    metrics = {k: None for k in METRIC_KEYS}
    url = str(row.get("post_url", ""))
    if not url:
        return metrics, "none", "post_url_missing"
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return metrics, "none", f"playwright_not_installed: {type(exc).__name__}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context_kwargs = {}
            if storage_state:
                context_kwargs["storage_state"] = storage_state
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            text = page.locator("body").inner_text(timeout=5_000)
            browser.close()
        metrics["likes"] = _first_int([r"(\d[\d,]*)\s+likes?", r"いいね\s*(\d[\d,]*)"], text)
        metrics["comments"] = _first_int([r"(\d[\d,]*)\s+repl(?:y|ies)", r"返信\s*(\d[\d,]*)"], text)
        metrics["reposts"] = _first_int([r"(\d[\d,]*)\s+reposts?", r"再投稿\s*(\d[\d,]*)"], text)
        if any(v is not None for v in metrics.values()):
            return metrics, "medium", "playwright_partial"
        return metrics, "none", "playwright_no_metrics"
    except Exception as exc:
        return metrics, "none", f"playwright_unavailable: {type(exc).__name__}"


def build_snapshot(*, row: dict[str, Any], source: str, confidence: str, metrics: dict[str, int | None], memo: str, error_reason: str = "") -> dict[str, Any]:
    known = {
        key: value
        for key, value in metrics.items()
        if value is not None
    }

    pdca_required_known = all(
        metrics.get(key) is not None
        for key in PDCA_REQUIRED_METRIC_KEYS
    )

    if pdca_required_known:
        status = "MEASURED"
    elif known:
        status = "PARTIAL"
    elif source == "unavailable" or error_reason:
        status = "UNAVAILABLE"
    else:
        status = "PENDING"
    collection_status = classify_collection_status(
        metrics=metrics,
        error_reason=error_reason,
    )

    snapshot_scope = str(
        row.get(
            "collection_job_id",
            "",
        )
        or row.get(
            "result_id",
            "unknown",
        )
        or "unknown"
    )

    snapshot_scope = re.sub(
        r"[^a-zA-Z0-9_]+",
        "_",
        snapshot_scope,
    ).strip("_")

    snapshot_stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d%H%M%S%f"
    )

    return {
        "snapshot_id": (
            f"ms_{snapshot_scope}_"
            f"{snapshot_stamp}"
        ),
        "result_id": row.get("result_id", ""),
        "account_id": row.get("account_id", ""),
        "platform": row.get("platform", "threads"),
        "post_url": row.get("post_url", ""),
        "collected_at": now_iso(),
        "source": source,
        "confidence": confidence,
        "metrics_status": status,
        "collection_status": collection_status,
        "collection_window_hours": row.get("collection_window_hours", ""),
        "collection_job_id": row.get("collection_job_id", ""),
        "memo": memo,
        "error_reason": error_reason,
        **{k: metrics.get(k) for k in METRIC_KEYS},
    }


def classify_collection_status(*, metrics: dict[str, int | None], error_reason: str) -> str:
    """Describe adapter availability without treating unknown values as zero."""
    known_count = sum(
        value is not None
        for value in metrics.values()
    )

    required_known = all(
        metrics.get(key) is not None
        for key in PDCA_REQUIRED_METRIC_KEYS
    )

    if required_known:
        return "AVAILABLE"

    if known_count:
        return "PARTIAL"
    reason = error_reason.lower()
    if "401" in reason or "403" in reason or "auth" in reason or "storage_state" in reason:
        return "AUTH_ERROR"
    if "404" in reason or "post_url_missing" in reason or "not found" in reason:
        return "POST_NOT_FOUND"
    if reason in {"", "unavailable", "no_adapter_requested"} or "no_metrics" in reason:
        return "NOT_AVAILABLE"
    return "COLLECTION_ERROR"


def collect_unavailable(row: dict[str, Any], source: str = "unavailable") -> dict[str, Any]:
    return build_snapshot(
        row=row,
        source=source,
        confidence="none",
        metrics={k: None for k in METRIC_KEYS},
        memo="Metrics collector could not obtain trusted values; unknowns left null.",
        error_reason="unavailable",
    )


def _headers(ws) -> list[str]:
    return ws.row_values(1)


def _append_row(client, logical: str, row: dict[str, Any]) -> bool:
    if logical == "metric_snapshots":
        from sheets_client import TAB_DEFINITIONS
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    ws = client._ws(logical)
    headers = _headers(ws)
    if not headers:
        return False
    ws.append_row(["" if row.get(h) is None else str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")
    return True


def _update_posted_result(
    client,
    result_id: str,
    snapshot: dict[str, Any],
) -> None:
    """Merge new evidence without downgrading an existing measured row."""

    ws = client._ws(
        "posted_results"
    )

    headers = _headers(ws)

    cell = ws.find(
        result_id,
        in_column=(
            headers.index(
                "result_id"
            )
            + 1
        ),
    )

    if cell is None:
        raise KeyError(
            f"result_id={result_id!r} "
            "not found"
        )

    existing_status = ""

    if "metrics_status" in headers:
        existing_status = str(
            ws.cell(
                cell.row,
                headers.index(
                    "metrics_status"
                )
                + 1,
            ).value
            or ""
        ).upper()

    for key in METRIC_KEYS:
        if key not in headers:
            continue

        value = snapshot.get(key)

        if value is None:
            continue

        ws.update_cell(
            cell.row,
            headers.index(key) + 1,
            str(value),
        )

    incoming_status = str(
        snapshot.get(
            "metrics_status",
            "",
        )
    ).upper()

    should_write_status = (
        incoming_status == "MEASURED"
        or (
            incoming_status == "PARTIAL"
            and existing_status
            != "MEASURED"
        )
    )

    if (
        should_write_status
        and "metrics_status" in headers
    ):
        ws.update_cell(
            cell.row,
            headers.index(
                "metrics_status"
            )
            + 1,
            incoming_status,
        )

    if "collected_at" in headers:
        ws.update_cell(
            cell.row,
            headers.index(
                "collected_at"
            )
            + 1,
            str(
                snapshot.get(
                    "collected_at",
                    "",
                )
            ),
        )

    if "measurement_window" in headers:
        window = snapshot.get(
            "collection_window_hours",
            "",
        )

        if window != "":
            ws.update_cell(
                cell.row,
                headers.index(
                    "measurement_window"
                )
                + 1,
                f"{window}h",
            )

    if "manual_memo" in headers:
        memo = str(
            snapshot.get("memo", "")
        )

        error_reason = str(
            snapshot.get(
                "error_reason",
                "",
            )
        )

        if error_reason:
            memo = (
                f"{memo} "
                f"error={error_reason}"
            ).strip()

        ws.update_cell(
            cell.row,
            headers.index(
                "manual_memo"
            )
            + 1,
            memo,
        )


def load_rows(use_sheets: bool, result_id: str | None, account_id: str) -> tuple[Any | None, list[dict[str, Any]]]:
    if not use_sheets:
        return None, []
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    rows = [dict(r) for r in client._ws("posted_results").get_all_records()]
    filtered = []
    for row in rows:
        if result_id and str(row.get("result_id", "")) != result_id:
            continue
        if account_id != "all" and str(row.get("account_id", "")) != account_id:
            continue
        if str(row.get("platform", "threads")).lower() != "threads":
            continue
        filtered.append(row)
    return client, filtered


def main() -> int:
    parser = argparse.ArgumentParser(description="collect Threads metrics safely")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--result-id")
    parser.add_argument("--source", default="unavailable", choices=["api", "browser", "manual", "unavailable"])
    parser.add_argument("--browser-engine", default="public", choices=["public", "playwright"],
                        help="browser source adapter. public uses urllib; playwright can use --storage-state.")
    parser.add_argument("--storage-state", default="",
                        help="Optional Playwright storage_state path. File contents are never printed.")
    parser.add_argument("--confidence", default="none", choices=["none", "low", "medium", "high"])
    for key in METRIC_KEYS:
        parser.add_argument(f"--{key.replace('_', '-')}", dest=key)
    parser.add_argument("--memo", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-metrics", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--post-url", action="append", default=[], help="Public Threads post URL for dry-run adapter checks")
    args = parser.parse_args()

    supplied = {key: parse_metric(getattr(args, key)) for key in METRIC_KEYS}
    if any(v is not None and v < 0 for v in supplied.values()):
        print(json.dumps({"status": "BLOCKED", "reason": "metrics must be >= 0"}, ensure_ascii=False))
        return 1

    client, rows = load_rows(args.use_sheets and (args.apply or args.dry_run), args.result_id, args.account_id)
    if args.post_url:
        rows = [
            {"result_id": args.result_id or f"url_{i}", "account_id": args.account_id, "platform": "threads", "post_url": url}
            for i, url in enumerate(args.post_url, 1)
        ]
    if not rows:
        rows = [{"result_id": args.result_id or "sample_result", "account_id": args.account_id, "platform": "threads", "post_url": ""}]

    snapshots = []
    for row in rows:
        error_reason = ""
        if any(v is not None for v in supplied.values()):
            metrics = supplied
            source = args.source
            confidence = args.confidence
            memo = args.memo or "operator supplied metrics"
        elif args.source == "api":
            account = str(
                row.get(
                    "account_id",
                    args.account_id,
                )
            )

            credentials = (
                resolve_credentials(
                    account
                )
            )

            (
                metrics,
                confidence,
                error_reason,
            ) = collect_api_threads_metrics(
                row,
                str(
                    credentials.get(
                        "access_token",
                        "",
                    )
                ),
            )

            source = "api"
            memo = (
                args.memo
                or (
                    "Official Threads post "
                    "insights; optional "
                    "conversion metrics remain "
                    "unknown."
                )
            )
        elif args.source == "browser":
            if (
                args.browser_engine
                == "playwright"
            ):
                (
                    metrics,
                    confidence,
                    error_reason,
                ) = (
                    collect_playwright_threads_metrics(
                        row,
                        args.storage_state,
                    )
                )
            else:
                (
                    metrics,
                    confidence,
                    error_reason,
                ) = (
                    collect_public_threads_metrics(
                        row,
                        args.source,
                    )
                )

            source = "browser"
            memo = (
                args.memo
                or (
                    "Public Threads browser "
                    "adapter; unknowns left "
                    "null."
                )
            )
        else:
            metrics = {k: None for k in METRIC_KEYS}
            source = "unavailable"
            confidence = "none"
            memo = args.memo or "metrics unavailable; no values fabricated"
            error_reason = "no_adapter_requested"
        snapshots.append(build_snapshot(row=row, source=source, confidence=confidence, metrics=metrics, memo=memo, error_reason=error_reason))

    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "adapter_status": dependency_status(), "snapshot_count": len(snapshots), "snapshots": snapshots}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_metrics:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-metrics"}, ensure_ascii=False))
        return 1
    if client is None:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --use-sheets"}, ensure_ascii=False))
        return 1

    appended = 0
    for snap in snapshots:
        if _append_row(client, "metric_snapshots", snap):
            appended += 1
        if snap["metrics_status"] in {"PARTIAL", "MEASURED", "UNAVAILABLE"}:
            _update_posted_result(client, str(snap["result_id"]), snap)
    print(json.dumps({"status": "APPLIED", "snapshot_count": appended, "result_ids": [s["result_id"] for s in snapshots]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
