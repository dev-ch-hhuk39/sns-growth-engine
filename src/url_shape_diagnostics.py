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
TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "si", "fbclid", "gclid", "igshid"}

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
    direct_identity_extracted = ident.confidence != "NONE"
    
    recovery_method = "NONE"
    recovered_ident = ident if direct_identity_extracted else None
    decoded_layer_count = 0
    has_nested_url = False

    for k, v_list in query_params.items():
        for v in v_list:
            if v.startswith("http://") or v.startswith("https://") or urllib.parse.unquote(v).startswith("http"):
                has_nested_url = True
                if not recovered_ident:
                    nested_ident = extract_source_post_identity(v)
                    if nested_ident.confidence != "NONE":
                        recovered_ident = nested_ident
                        recovery_method = "NESTED_QUERY_URL"

    if not recovered_ident:
        decoded_url = url
        for i in range(1, 3):
            next_decoded = urllib.parse.unquote(decoded_url)
            if next_decoded == decoded_url:
                break
            decoded_url = next_decoded
            nested_ident = extract_source_post_identity(decoded_url)
            if nested_ident.confidence != "NONE":
                recovered_ident = nested_ident
                recovery_method = "PERCENT_DECODED_URL"
                decoded_layer_count = i
                break
                
    if not recovered_ident:
        if path_family == "EMBED" and host_family == "YOUTUBE":
            parts = path.strip("/").split("/")
            if len(parts) >= 2 and parts[1]:
                fake_url = f"https://www.youtube.com/watch?v={parts[1]}"
                nested_ident = extract_source_post_identity(fake_url)
                if nested_ident.confidence != "NONE":
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
    host = host.split(":")[0]  # strip port
    if host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        return "YOUTUBE"
    if host in ("youtu.be", "www.youtu.be"):
        return "YOUTU_BE"
    if host in ("threads.net", "www.threads.net", "threads.com", "www.threads.com"):
        return "THREADS"
    if host in ("tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"):
        return "TIKTOK"
    if host in ("google.com", "www.google.com") or host.endswith(".google.com"):
        return "GOOGLE_REDIRECT"
    return "OTHER"

def _determine_path_family(path: str, host_family: str) -> str:
    path = path.strip("/")
    if not path:
        return "ROOT"
    
    parts = path.split("/")
    first = parts[0].lower()

    if host_family == "YOUTUBE":
        if first == "watch": return "WATCH"
        if first == "shorts": return "SHORTS"
        if first == "live": return "LIVE"
        if first == "embed": return "EMBED"
        if first == "channel": return "CHANNEL"
        if first == "user": return "USER"
        if first == "playlist": return "PLAYLIST"
        if first.startswith("@"): return "HANDLE"
        return "OTHER"

    if host_family == "TIKTOK":
        if "video" in parts: return "TIKTOK_VIDEO"
        if first.startswith("@"):
            if len(parts) > 1 and parts[1] == "video":
                return "TIKTOK_VIDEO"
            return "HANDLE"
        return "OTHER"

    if host_family == "THREADS":
        if "post" in parts: return "THREADS_POST"
        if first.startswith("@"):
            if len(parts) > 1 and parts[1] == "post":
                return "THREADS_POST"
            return "HANDLE"
        return "OTHER"

    if host_family == "GOOGLE_REDIRECT":
        if first == "url": return "REDIRECT"
        return "OTHER"
        
    return "OTHER"

def _normalize_url_string(url: str) -> str:
    if not url or not str(url).strip():
        return ""
    try:
        decoded = url
        for _ in range(2):
            next_decoded = urllib.parse.unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
            
        parsed = urllib.parse.urlparse(decoded)
        if not parsed.scheme and not parsed.netloc and not url.startswith("http"):
            parsed = urllib.parse.urlparse("https://" + decoded)
    except Exception:
        parsed = urllib.parse.urlparse("http://malformed")

    scheme = parsed.scheme.lower() if parsed.scheme else "https"
    host = parsed.netloc.lower() if parsed.netloc else ""
    path = parsed.path if parsed.path else ""
    
    query_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True) if parsed.query else []
    new_query = []
    
    for k, v in query_params:
        if k.lower() not in TRACKING_KEYS:
            new_query.append((k, v))
            
    new_qs = urllib.parse.urlencode(new_query)
    return urllib.parse.urlunparse((scheme, host, path, "", new_qs, ""))

def normalize_url_for_safe_grouping(url: str) -> str:
    normalized = _normalize_url_string(url)
    if not normalized:
        return ""
    return "URL_GROUP_" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
