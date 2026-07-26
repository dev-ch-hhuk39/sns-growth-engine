import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pytest
from src.url_shape_diagnostics import parse_url_shape, normalize_url_for_safe_grouping, _normalize_url_string

def test_parse_youtube_watch():
    shape = parse_url_shape("https://www.youtube.com/watch?v=12345678901")
    assert shape.input_state == "ABSOLUTE_URL"
    assert shape.host_family == "YOUTUBE"
    assert shape.path_family == "WATCH"
    assert "v" in shape.has_allowed_query_keys
    assert shape.direct_identity_extracted is True
    assert shape.recovery_method == "DIRECT"
    assert shape.recovered_platform == "youtube"

def test_parse_youtu_be():
    shape = parse_url_shape("https://youtu.be/12345678901")
    assert shape.host_family == "YOUTU_BE"
    assert shape.direct_identity_extracted is True
    assert shape.recovery_method == "DIRECT"

def test_parse_tiktok():
    shape = parse_url_shape("https://www.tiktok.com/@user/video/1234567890")
    assert shape.host_family == "TIKTOK"
    assert shape.path_family == "TIKTOK_VIDEO"
    assert shape.direct_identity_extracted is True
    assert shape.recovery_method == "DIRECT"

def test_parse_malformed():
    shape = parse_url_shape("://malformed")
    assert shape.input_state == "MALFORMED"

def test_parse_scheme_missing():
    shape = parse_url_shape("www.youtube.com/watch?v=12345678901")
    assert shape.input_state == "SCHEME_MISSING"
    assert shape.host_family == "YOUTUBE"
    assert shape.direct_identity_extracted is True
    assert shape.recovery_method == "DIRECT"

def test_nested_url_percent_decoded():
    outer = f"https%253A%252F%252Fwww.youtube.com%252Fwatch%253Fv%253D12345678901"
    shape = parse_url_shape(outer)
    assert shape.direct_identity_extracted is False
    assert shape.recovery_method == "PERCENT_DECODED_URL"
    assert shape.decoded_layer_count == 2
    assert shape.recovered_platform == "youtube"

def test_nested_query():
    url = "https://www.google.com/url?q=https://www.youtube.com/watch?v=12345678901"
    shape = parse_url_shape(url)
    assert shape.has_nested_url is True
    assert shape.recovery_method == "NESTED_QUERY_URL"
    assert shape.recovered_platform == "youtube"

def test_normalize():
    url = "https://www.youtube.com/watch?v=12345678901&utm_source=test"
    norm = _normalize_url_string(url)
    assert "utm_source" not in norm
    assert "v=12345678901" in norm
    safe_group = normalize_url_for_safe_grouping(url)
    assert safe_group.startswith("URL_GROUP_")
    assert len(safe_group) > 20

