"""Allowlisted Google quota metadata; never retain error messages or subjects.

Unknown identifiers are omitted rather than copied from an untrusted error body.
Only the Vision transport uses the retry policy; text/production policy is unchanged.
"""
from __future__ import annotations

import json
import re
from typing import Any

FIELDS = ('provider_http_status', 'provider_error_status', 'rate_limit_class',
          'quota_metric', 'quota_id', 'quota_model', 'quota_location',
          'quota_limit_value', 'retry_delay_seconds')
_WORDS = set('generate content requests request input output tokens token per minute day project model free paid tier batch cached cache spend spending dollars cost limit quota total count'.split())


def _identifier(value: Any, *, metric: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 200:
        return ''
    tail = value
    if metric:
        prefix = 'generativelanguage.googleapis.com/'
        if not value.startswith(prefix):
            return ''
        tail = value[len(prefix):]
    words = re.sub(r'([a-z])([A-Z])', r'\1 \2', tail).lower()
    words = re.split(r'[_\s-]+', words)
    return value if words and all(word in _WORDS for word in words) else ''


def _number(value: Any) -> int | str:
    if isinstance(value, bool):
        return ''
    text = str(value)
    return int(text) if re.fullmatch(r'\d{1,18}', text) else ''


def _classify(row: dict) -> str:
    evidence = re.sub(r'[^a-z]', '', (row['quota_id'] + row['quota_metric']).lower())
    if 'spend' in evidence or 'dollars' in evidence or 'cost' in evidence:
        return 'SPEND_RATE_LIMIT'
    if 'perday' in evidence:
        return 'DAILY_QUOTA_EXHAUSTED'
    if row['quota_limit_value'] == 0 and (row['quota_model'] or 'permodel' in evidence):
        return 'MODEL_QUOTA_EXHAUSTED'
    if 'token' in evidence and 'perminute' in evidence:
        return 'TOKEN_RATE_LIMIT'
    if 'perminute' in evidence:
        return 'PER_MINUTE_RATE_LIMIT'
    if 'permodel' in evidence:
        return 'MODEL_QUOTA_EXHAUSTED'
    return 'RATE_LIMIT_UNKNOWN'


def safe_quota_diagnostics(status: int, body: str) -> dict:
    result = {key: '' for key in FIELDS}
    result.update(provider_http_status=status, rate_limit_class='RATE_LIMIT_UNKNOWN' if status == 429 else '')
    if status != 429:
        return result
    try:
        error = json.loads(body).get('error', {})
        if not isinstance(error, dict):
            return result
    except (ValueError, TypeError, AttributeError):
        return result
    if error.get('status') == 'RESOURCE_EXHAUSTED':
        result['provider_error_status'] = 'RESOURCE_EXHAUSTED'
    details = error.get('details', [])
    if not isinstance(details, list):
        return result
    rows, delays = [], []
    for detail in details:
        if not isinstance(detail, dict):
            continue
        if detail.get('@type') == 'type.googleapis.com/google.rpc.RetryInfo':
            delay = detail.get('retryDelay')
            if isinstance(delay, str) and re.fullmatch(r'\d{1,9}(?:\.\d{1,9})?s', delay):
                delays.append(float(delay[:-1]))
        if detail.get('@type') != 'type.googleapis.com/google.rpc.QuotaFailure':
            continue
        violations = detail.get('violations', [])
        if not isinstance(violations, list):
            continue
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            dims = violation.get('quotaDimensions', {})
            dims = dims if isinstance(dims, dict) else {}
            model = dims.get('model', '')
            location = dims.get('location', '')
            row = {
                'quota_metric': _identifier(violation.get('quotaMetric'), metric=True),
                'quota_id': _identifier(violation.get('quotaId')),
                'quota_model': model if isinstance(model, str) and re.fullmatch(r'gemini-\d+(?:\.\d+)?-(?:flash|pro)(?:-lite)?(?:-preview(?:-\d{2}-\d{2})?)?', model) else '',
                'quota_location': location if isinstance(location, str) and re.fullmatch(r'global|us|eu|(?:us|europe|asia|australia|northamerica|southamerica|africa|me)-(?:central|east|west|north|south|northeast|southeast|southwest)\d', location) else '',
                'quota_limit_value': _number(violation.get('quotaValue')),
            }
            row['rate_limit_class'] = _classify(row)
            rows.append(row)
    # The strongest stop condition wins; keep every safe violation for diagnosis.
    priority = {'SPEND_RATE_LIMIT': 0, 'DAILY_QUOTA_EXHAUSTED': 1,
                'MODEL_QUOTA_EXHAUSTED': 3, 'TOKEN_RATE_LIMIT': 4,
                'PER_MINUTE_RATE_LIMIT': 5, 'RATE_LIMIT_UNKNOWN': 6}
    if rows:
        selected = min(rows, key=lambda row: 2 if row['quota_limit_value'] == 0 and priority[row['rate_limit_class']] > 1 else priority[row['rate_limit_class']])
        result.update(selected)
        result['quota_violations'] = rows
    if delays:
        result['retry_delay_seconds'] = max(delays)
    return result


def vision_retry_decision(diagnostics: dict, attempt: int) -> tuple[str, float | None]:
    kind = diagnostics.get('rate_limit_class')
    if kind == 'DAILY_QUOTA_EXHAUSTED' or diagnostics.get('quota_limit_value') == 0:
        return 'NO_RETRY', None
    delay = diagnostics.get('retry_delay_seconds', '')
    if kind == 'SPEND_RATE_LIMIT' or (isinstance(delay, (float, int)) and delay > 60):
        return 'RETRY_DEFERRED', None
    if attempt >= 3:
        return 'ATTEMPTS_EXHAUSTED', None
    # Unknown 429 retains the existing <=3 attempts fallback, never unbounded.
    return 'RETRY', float(delay) if isinstance(delay, (float, int)) else (5, 15)[attempt - 1]
