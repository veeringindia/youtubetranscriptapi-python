"""Official Python client for YouTubeTranscriptAPI (https://youtubetranscriptapi.com).

Fetch YouTube transcripts, search YouTube, and list channel and playlist
videos through the hosted REST API. No YouTube IP blocks or 429s to handle.
"""

from ._client import DEFAULT_BASE_URL, ResponseInfo, YouTubeTranscriptAPI, segments
from ._errors import (
    AuthenticationError,
    InsufficientCreditsError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    TransientError,
    ValidationError,
    YouTubeTranscriptAPIError,
)
from ._version import __version__

__all__ = [
    "YouTubeTranscriptAPI",
    "ResponseInfo",
    "segments",
    "DEFAULT_BASE_URL",
    "YouTubeTranscriptAPIError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "RateLimitError",
    "TransientError",
    "__version__",
]
