"""Strict multimodal JSON parsing with diagnostics containing no response values."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping


class VisionResponseError(RuntimeError):
    def __init__(self, stage: str, raw_type: str, *, code: str = 'INVALID_RESPONSE', **details: Any):
        super().__init__(code)
        self.status_code = 200
        self.diagnostics = {'parse_stage': stage, 'raw_response_type': raw_type,
                            'failure_class': code.lower(), 'response_schema_status': 'INVALID', **details}


def parse_vision_response(response: Any, schema: Mapping[str, Any], *, api_key: str) -> tuple[dict, dict]:
    raw_type = type(response).__name__
    def fail(stage: str, **details: Any):
        raise VisionResponseError(stage, raw_type, **details)

    if not isinstance(response, dict):
        fail('response_envelope', schema_error='EXPECTED_OBJECT')
    candidates = response.get('candidates')
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        fail('response_envelope', missing_fields=['candidates'])
    content = candidates[0].get('content')
    if not isinstance(content, dict) or not isinstance(content.get('parts'), list):
        fail('response_envelope', missing_fields=['candidates[0].content.parts'])
    parts = [p for p in content['parts'] if isinstance(p, dict) and p.get('thought') is not True and 'text' in p]
    if not parts or any(not isinstance(p['text'], str) for p in parts):
        fail('response_envelope', schema_error='EXPECTED_TEXT_PART')
    raw = '\n'.join(p['text'] for p in parts).strip()
    raw_type = 'string'
    if api_key and api_key in raw:
        fail('json_parse', schema_error='CREDENTIAL_ECHO_REDACTED')
    fence = re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```', raw, flags=re.IGNORECASE)
    if fence:
        raw = fence[1].strip()
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        fail('json_parse', schema_error='JSON_PARSE_FAILURE')
    if api_key and api_key in json.dumps(data, ensure_ascii=False):
        fail('json_parse', schema_error='CREDENTIAL_ECHO_REDACTED')
    if not isinstance(data, dict):
        fail('json_parse', schema_error='EXPECTED_OBJECT', actual_type=type(data).__name__)
    normalizations = []
    if 'visible_actions' in data:
        alias = data['visible_actions']
        if isinstance(alias, list) and alias and all(isinstance(x, str) for x in alias):
            alias = '\n'.join(alias)
        if not isinstance(alias, str):
            fail('normalization', schema_error='TYPE_MISMATCH', field='visible_action', expected_type='string')
        if 'visible_action' in data and data['visible_action'] != alias:
            fail('normalization', schema_error='CONFLICTING_ALIAS', field='visible_action')
        data['visible_action'] = alias
        del data['visible_actions']
        normalizations.append('visible_actions->visible_action')

    def validate(value: Any, spec: Mapping[str, Any], path: str):
        expected = spec.get('type')
        types = {'object': dict, 'array': list, 'string': str}
        if expected in types and not isinstance(value, types[expected]):
            fail('schema_validation', schema_error='TYPE_MISMATCH', field=path,
                 expected_type=expected, actual_type=type(value).__name__)
        if expected == 'object':
            missing = [f'{path}.{k}' if path else k for k in spec.get('required', []) if k not in value]
            if missing:
                fail('schema_validation', code='SCHEMA_MISSING_FIELD', missing_fields=missing)
            properties = spec.get('properties', {})
            if spec.get('additionalProperties') is False and set(value) - set(properties):
                # Never include unknown field names: they are provider-controlled text.
                fail('schema_validation', schema_error='UNEXPECTED_FIELDS', field=path)
            for key, child in properties.items():
                if key in value:
                    validate(value[key], child, f'{path}.{key}' if path else key)
        elif expected == 'array':
            if len(value) < spec.get('minItems', 0):
                fail('schema_validation', schema_error='EMPTY_ARRAY', field=path)
            for i, item in enumerate(value):
                validate(item, spec.get('items', {}), f'{path}[{i}]')
        elif expected == 'string':
            if 'enum' in spec and value not in spec['enum']:
                fail('schema_validation', schema_error='INVALID_ENUM', field=path)
            if len(value) < spec.get('minLength', 0):
                fail('schema_validation', schema_error='EMPTY_STRING', field=path)
    validate(data, schema, '')
    return data, {'raw_response_type': raw_type, 'parse_stage': 'complete',
                  'response_schema_status': 'PASS', 'normalizations': normalizations}
