"""The YouTubeTranscriptAPI client. Standard library only."""

from __future__ import annotations

import json
import os
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Union

from ._errors import (
    AuthenticationError,
    TransientError,
    YouTubeTranscriptAPIError,
    error_for_status,
)
from ._version import __version__

DEFAULT_BASE_URL = "https://youtubetranscriptapi.com/api/v2"
SIGNUP_URL = "https://youtubetranscriptapi.com/signup?ref=pypi"
ENV_VARS = ("YTT_API_KEY", "YT_API_KEY")

# Statuses the API documents as safe to retry, and how long to wait at most.
_RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
_MAX_RETRY_WAIT = 30.0

JSON = Dict[str, Any]


@dataclass(frozen=True)
class ResponseInfo:
    """Headers of the most recent successful call (``client.last_response``)."""

    status: int
    credits_charged: Optional[int]
    credits_remaining: Optional[int]
    cache_status: Optional[str]
    rate_limit_remaining: Optional[int]
    request_id: Optional[str]


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


class YouTubeTranscriptAPI:
    """Client for the hosted YouTubeTranscriptAPI REST API.

    >>> from youtubetranscriptapi import YouTubeTranscriptAPI
    >>> yt = YouTubeTranscriptAPI()  # reads YTT_API_KEY
    >>> yt.transcript("dQw4w9WgXcQ")["transcript"][0]["text"]

    Args:
        api_key: Your ``tk_live_`` key. Defaults to the ``YTT_API_KEY``
            environment variable (or ``YT_API_KEY``).
        timeout: Seconds to wait for each request. A video fetched for the
            first time can take 10-30 seconds, so keep this at 60 or more.
        max_retries: Retries for 408, 429 and 5xx responses and network
            errors, honouring ``Retry-After``. Failed calls are never charged.
        base_url: Override the API root (for testing).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        timeout: float = 60.0,
        max_retries: int = 2,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        key = api_key or next((os.environ[v] for v in ENV_VARS if os.environ.get(v)), None)
        if not key:
            raise AuthenticationError(
                "No API key. Pass api_key=... or set YTT_API_KEY. "
                f"Get a free key (100 credits, no card) at {SIGNUP_URL}"
            )
        self.api_key = key
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.base_url = base_url.rstrip("/")
        self.last_response: Optional[ResponseInfo] = None

    def __repr__(self) -> str:
        return f"YouTubeTranscriptAPI(api_key='{self.api_key[:8]}…', base_url='{self.base_url}')"

    # ---- Endpoints -------------------------------------------------------

    def transcript(
        self,
        video: str,
        *,
        language: str = "en",
        timestamps: bool = True,
        metadata: bool = False,
    ) -> JSON:
        """A video's transcript as segments. 1 credit.

        Args:
            video: Video ID, youtube.com URL or youtu.be URL.
            language: Preferred caption language. If the video has no track in
                it, another may come back; check the ``language`` field.
            timestamps: Include ``start`` and ``duration`` on each segment.
            metadata: Include title, author and thumbnail under ``metadata``.

        Returns:
            ``{"video_id", "language", "transcript": [{"text", "start", "duration"}, ...]}``
        """
        return self._get(
            "/youtube/transcript",
            video_url=video,
            language=language,
            format="json",
            include_timestamp=timestamps,
            send_metadata=metadata,
        )

    def transcript_text(self, video: str, *, language: str = "en", timestamps: bool = False) -> str:
        """A video's transcript as one string. 1 credit.

        With ``timestamps=True`` each line starts with ``[12.3s]``.
        """
        data = self._get(
            "/youtube/transcript",
            video_url=video,
            language=language,
            format="text",
            include_timestamp=timestamps,
        )
        return data["transcript"]

    def search(self, query: str, *, type: str = "video", limit: int = 20) -> JSON:
        """Search YouTube for videos or channels (``type="channel"``). 4 credits."""
        return self._get("/youtube/search", q=query, type=type, limit=limit)

    def search_channel(self, channel: str, query: str, *, limit: int = 30) -> JSON:
        """Search one channel's videos. ``channel`` is an @handle, URL or UC… ID. 1 credit."""
        return self._get("/youtube/channel/search", channel=channel, q=query, limit=limit)

    def channel_videos(self, channel: str) -> JSON:
        """A channel's most recent uploads, up to 100. 20 credits."""
        return self._get("/youtube/channel/videos", channel=channel)

    def latest_videos(self, channel: str) -> JSON:
        """A channel's 15 newest uploads (RSS). Free; needs at least 1 credit."""
        return self._get("/youtube/channel/latest", channel=channel)

    def resolve_channel(self, channel: str) -> str:
        """An @handle or channel URL to its UC… channel ID. Free; needs at least 1 credit."""
        return self._get("/youtube/channel/resolve", input=channel)["channel_id"]

    def playlist_videos(self, playlist: str) -> JSON:
        """Up to 100 videos of a playlist (ID or URL with ``list=``). 20 credits."""
        return self._get("/youtube/playlist/videos", playlist=playlist)

    def account(self) -> JSON:
        """Your plan and credit balance. Free."""
        return self._get("/account/whoami")

    # ---- Transport -------------------------------------------------------

    def _url(self, path: str, params: Mapping[str, Any]) -> str:
        query = {}
        for k, v in params.items():
            if v is None:
                continue
            query[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
        qs = urllib.parse.urlencode(query)
        return f"{self.base_url}{path}" + (f"?{qs}" if qs else "")

    def _get(self, path: str, **params: Any) -> Any:
        url = self._url(path, params)
        attempt = 0
        while True:
            try:
                return self._request(url)
            except YouTubeTranscriptAPIError as err:
                retryable = err.status is None or err.status in _RETRY_STATUSES
                if not retryable or attempt >= self.max_retries:
                    raise
                wait = err.retry_after if err.retry_after is not None else min(2 ** attempt, 8) + random.random()
                time.sleep(min(wait, _MAX_RETRY_WAIT))
                attempt += 1

    def _request(self, url: str) -> Any:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "User-Agent": f"youtubetranscriptapi-python/{__version__}",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                body = res.read()
                headers = res.headers
                status = res.status
        except urllib.error.HTTPError as e:
            raise self._error(e.code, e.read(), e.headers) from None
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            reason = getattr(e, "reason", e)
            raise TransientError(f"Request failed before a response: {reason}") from e

        self.last_response = ResponseInfo(
            status=status,
            credits_charged=_int(headers.get("X-Credits-Charged")),
            credits_remaining=_int(headers.get("X-Credits-Remaining")),
            cache_status=headers.get("X-Cache-Status"),
            rate_limit_remaining=_int(headers.get("X-RateLimit-Remaining")),
            request_id=headers.get("X-Request-Id"),
        )
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError:
            raise YouTubeTranscriptAPIError(
                "The API returned a response that isn't JSON", status=status
            ) from None

    @staticmethod
    def _error(status: int, body: bytes, headers: Any) -> YouTubeTranscriptAPIError:
        code = None
        detail: Any = None
        message = f"HTTP {status}"
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:
            data = None
        if isinstance(data, dict):
            code = data.get("code")
            detail = data.get("detail")
            if isinstance(detail, dict):
                message = str(detail.get("message") or message)
            elif detail:
                message = str(detail)
        cls = error_for_status(status)
        return cls(
            message,
            status=status,
            code=code,
            detail=detail,
            request_id=headers.get("X-Request-Id") if headers else None,
            retry_after=_float(headers.get("Retry-After")) if headers else None,
        )


def segments(data: JSON) -> List[Dict[str, Union[str, float]]]:
    """The segment list of a ``transcript()`` result."""
    return list(data.get("transcript") or [])
