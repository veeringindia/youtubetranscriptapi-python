"""Exceptions raised by the client. Every API error is a YouTubeTranscriptAPIError."""

from __future__ import annotations

from typing import Any, Dict, Optional


class YouTubeTranscriptAPIError(Exception):
    """An error response from the API, or a request that never got one.

    Attributes:
        status: HTTP status code, or None when the request failed before a response.
        code: The API's error code, such as ``transcript_not_found``.
        message: A human-readable message.
        detail: The raw ``detail`` field. For 402 errors it's a dict with
            ``action_url``, ``required``, ``available`` and plan prices.
        request_id: The ``X-Request-Id`` header, useful when contacting support.
        retry_after: Seconds to wait before retrying, from ``Retry-After``.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        detail: Any = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.detail = detail
        self.request_id = request_id
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [self.message]
        if self.status is not None:
            parts.append(f"(HTTP {self.status}" + (f", {self.code})" if self.code else ")"))
        return " ".join(parts)


class AuthenticationError(YouTubeTranscriptAPIError):
    """401: the API key is missing, invalid or revoked."""


class InsufficientCreditsError(YouTubeTranscriptAPIError):
    """402: not enough credits for this call.

    ``action_url`` links to the page that fixes it (a plan or a top-up).
    """

    @property
    def action_url(self) -> Optional[str]:
        return self.detail.get("action_url") if isinstance(self.detail, dict) else None

    @property
    def checkout_url(self) -> Optional[str]:
        return self.detail.get("checkout_url") if isinstance(self.detail, dict) else None


class PermissionDeniedError(YouTubeTranscriptAPIError):
    """403: the account is paused."""


class NotFoundError(YouTubeTranscriptAPIError):
    """404: no captions, or the video, channel or playlist is private or gone."""


class ValidationError(YouTubeTranscriptAPIError):
    """422: a parameter is missing or invalid."""


class RateLimitError(YouTubeTranscriptAPIError):
    """429: too many requests. Wait ``retry_after`` seconds."""


class TransientError(YouTubeTranscriptAPIError):
    """408, 500 or 503, or a network failure: safe to retry."""


_BY_STATUS: Dict[int, type] = {
    401: AuthenticationError,
    402: InsufficientCreditsError,
    403: PermissionDeniedError,
    404: NotFoundError,
    422: ValidationError,
    429: RateLimitError,
    408: TransientError,
    500: TransientError,
    502: TransientError,
    503: TransientError,
    504: TransientError,
}


def error_for_status(status: int) -> type:
    return _BY_STATUS.get(status, YouTubeTranscriptAPIError)
