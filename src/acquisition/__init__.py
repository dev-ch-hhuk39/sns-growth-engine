"""Normalized, replaceable social acquisition adapters.

Production callers use this package instead of coupling Sheets or posting code
to a scraper implementation.  Adapters only discover public source material;
permission, download, Cloudinary and publishing remain separate gates.
"""

from .models import NormalizedMediaItem, NormalizedSourcePost, validate_source_post
from .router import AdapterRouter, BackendFailure, BackendRoute

__all__ = [
    "AdapterRouter",
    "BackendFailure",
    "BackendRoute",
    "NormalizedMediaItem",
    "NormalizedSourcePost",
    "validate_source_post",
]
