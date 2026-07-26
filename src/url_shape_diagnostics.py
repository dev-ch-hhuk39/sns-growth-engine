import urllib.parse
from dataclasses import dataclass
from typing import Optional, Tuple
import hashlib
from src.source_post_identity import extract_source_post_identity, SourcePostIdentity

@dataclass(frozen=True)
class SafeUrlShape:
    input_state: str
    host_family: str
    path_family: str
    has_allowed_query_keys: tuple[str, ...]
    has_nested_url: bool
    decoded_layer_count: int
    direct_identity_extracted: bool
    recovery_method: str
    recovered_platform: str
    recovered_identity_kind: str
    recovered_stable_post_id: str

ALLOWED_QUERY_KEYS = {"v", "url", "q", "u", "target", "list"}
NESTED_URL_KEYS = {"url", "q", "u", "target"}

def parse_url_shape(url: str) -> SafeUrlShape:
    if not url or not str(url).strip():
        return SafeUrlShape("EMPTY", "NONE", "NONE", (), False, 0, False, "NONE", "", "", "")

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return SafeUrlShape("MALFORMED", "NONE", "NONE", (), False, 0, False, "NONE", "", "", "")

    input_state = "ABSOLUTE_URL"
    if not parsed.scheme and not parsed.netloc:
        if "/" in url or "?" in url:
            if not url.startswith("http") and not url.startswith("://"):
                parsed2 = urllib.parse.urlparse("https://" + url)
                if parsed2.netloc:
                    input_state = "SCHEME_MISSING"
                    parsed = parsed2
        if input_state == "ABSOLUTE_URL":
            input_state = "MALFORMED"
    else:
        if not parsed.scheme or not parsed.netloc:
            input_state = "MALFORMED"
            
    host = parsed.netloc.lower() if parsed.netloc else ""
    host_family = _determine_host_family(host)
    path = parsed.path if parsed.path else ""
    path_family = _determine_path_family(path, host_family)
    
    query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True) if parsed.query else {}
    found_keys = tuple(sorted(k for k in query_params.keys() if k in ALLOWED_QUERY_KEYS))

    ident = extract_source_post_identity(url)
    direct_identity_extracted = ident.confidence == "HIGH"
    
    recovery_method = "NONE"
    recovered_ident = ident if direct_identity_extracted else None
    decoded_layer_count = 0
    has_nested_url = False

    for k, v_list in query_params.items():
        if k not in NESTED_URL_KEYS:
            continue
        for v in v_list:
            if v.startswith("http://") or v.startswith("https://") or urllib.parse.unquote(v).startswith("http"):
                has_nested_url = True
                if not recovered_ident:
                    nested_ident = extract_source_post_identity(v)
                    if nested_ident.confidence == "HIGH":
                        recovered_ident = nested_ident
                        recovery_method = "NESTED_QUERY_URL"

    if not recovered_ident:
        decoded_url = url
        for i in range(1, 3):
            next_decoded = urllib.parse.unquote(decoded_url)
            if next_decoded == decoded_url:
                break
            decoded_url = next_decoded
            decoded_layer_count = i
            nested_ident = extract_source_post_identity(decoded_url)
            if nested_ident.confidence == "HIGH":
                recovered_ident = nested_ident
                recovery_method = "PERCENT_DECODED_URL"
                break
                
    if not recovered_ident:
        if path_family == "EMBED" and host_family == "YOUTUBE":
            parts = path.strip("/").split("/")
            if len(parts) >= 2 and parts[1]:
                fake_url = f"https://www.youtube.com/watch?v={parts[1]}"
                nested_ident = extract_source_post_identity(fake_url)
                if nested_ident.confidence == "HIGH":
                    recovered_ident = nested_ident
                    recovery_method = "EMBED_PATH"

    if recovered_ident and recovery_method == "NONE":
        recovery_method = "DIRECT"

    return SafeUrlShape(
        input_state=input_state,
        host_family=host_family,
        path_family=path_family,
        has_allowed_query_keys=found_keys,
        has_nested_url=has_nested_url,
        decoded_layer_count=decoded_layer_count,
        direct_identity_extracted=direct_identity_extracted,
        recovery_method=recovery_method,
        recovered_platform=recovered_ident.platform if recovered_ident else "",
        recovered_identity_kind=recovered_ident.identity_kind if recovered_ident else "",
        recovered_stable_post_id=recovered_ident.stable_post_id if recovered_ident else ""
    )

def _determine_host_family(host: str) -> str:
    if not host:
        return "NONE"
    host = host.split(":")[0]
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        return "YOUTUBE"
    if host in ("youtu.be", "www.youtu.be"):
        return "YOUTU_BE"
    if host in ("threads.net", "www.threads.net", "threads.com", "www.threads.com"):
        return "THREADS"
    if host in ("tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"):
        return "TIKTOK"
    if host in ("google.com", "www.google.com"):
        return "GOOGLE_REDIRECT"
    return "OTHER"

def _determine_path_family(path: str, host_family: str) -> str:
    path = path.strip("/")
    if not path:
        return "ROOT"
    
    parts = path.split("/")
    first = parts[0].lower()

    if host_family == "YOUTUBE":
        if first == "watch" and len(parts) == 1: return "WATCH"
        if first == "shorts" and len(parts) == 2: return "SHORTS"
        if first == "live" and len(parts) == 2: return "LIVE"
        if first == "embed" and len(parts) == 2: return "EMBED"
        if first == "channel" and len(parts) == 2: return "CHANNEL"
        if first == "user" and len(parts) == 2: return "USER"
        if first == "playlist" and len(parts) == 1: return "PLAYLIST"
        if first.startswith("@") and len(parts) == 1: return "HANDLE"
        return "OTHER"

    if host_family == "TIKTOK":
        if len(parts) == 3 and parts[0].startswith("@") and parts[1] == "video": return "TIKTOK_VIDEO"
        if len(parts) == 1 and parts[0].startswith("@"): return "HANDLE"
        return "OTHER"

    if host_family == "THREADS":
        if len(parts) == 3 and parts[0].startswith("@") and parts[1] == "post": return "THREADS_POST"
        if len(parts) == 1 and parts[0].startswith("@"): return "HANDLE"
        return "OTHER"

    if host_family == "GOOGLE_REDIRECT":
        if first == "url" and len(parts) == 1: return "REDIRECT"
        return "OTHER"
        
    return "OTHER"

def _normalize_url_string(url: str, is_media: bool = False) -> str:
    if not url or not str(url).strip():
        return ""
        
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        parsed = urllib.parse.urlparse("http://malformed")

    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    host = parsed.netloc.lower() if parsed.netloc else ""
    path = parsed.path if parsed.path else ""
    
    if is_media:
        return f"{scheme}://{host}{path}"
        
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if parsed.query else []
    
    for k, v in query_params:
        if k in NESTED_URL_KEYS:
            if v.startswith("http"):
                nested = _normalize_url_string(v)
                if nested: return nested
                
    new_query = []
    for k, v in query_params:
        if k in ALLOWED_QUERY_KEYS and k not in NESTED_URL_KEYS:
            new_query.append((k, v))
            
    new_query.sort()
    new_qs = urllib.parse.urlencode(new_query)
    return f"{scheme}://{host}{path}?{new_qs}" if new_qs else f"{scheme}://{host}{path}"

def _safe_hash(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()

def normalize_url_for_safe_grouping(url: str) -> str:
    normalized = _normalize_url_string(url, is_media=False)
    if not normalized:
        return ""
    return _safe_hash(normalized)

def normalize_media_url_for_fingerprint(url: str) -> str:
    normalized = _normalize_url_string(url, is_media=True)
    if not normalized:
        return ""
    return _safe_hash(normalized)
