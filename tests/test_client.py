"""Tests against a local fake of the API (no network, no credits)."""

import contextlib
import io
import json
import os
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib.parse import parse_qs, urlparse

from youtubetranscriptapi import (
    AuthenticationError,
    InsufficientCreditsError,
    NotFoundError,
    RateLimitError,
    TransientError,
    YouTubeTranscriptAPI,
    __version__,
    segments,
)
from youtubetranscriptapi.cli import main as cli_main

KEY = "tk_live_" + "A" * 32


class FakeAPI(BaseHTTPRequestHandler):
    """Serves queued (status, body, headers) replies and records requests."""

    replies = []  # type: list
    requests = []  # type: list

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        FakeAPI.requests.append(
            {"path": url.path, "query": {k: v[0] for k, v in parse_qs(url.query).items()},
             "headers": dict(self.headers)}
        )
        status, body, headers = FakeAPI.replies.pop(0) if FakeAPI.replies else (500, b"no reply queued", {})
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class ClientTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), FakeAPI)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/api/v2"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeAPI.replies = []
        FakeAPI.requests = []

    def client(self, **kw):
        return YouTubeTranscriptAPI(KEY, base_url=self.base, **kw)

    def queue(self, status, body, **headers):
        FakeAPI.replies.append((status, body, headers))

    # ---- Requests and parsing -------------------------------------------

    def test_transcript_sends_params_and_auth(self):
        body = {"video_id": "dQw4w9WgXcQ", "language": "en",
                "transcript": [{"text": "Hi", "start": 0, "duration": 1.5}]}
        self.queue(200, body, **{"X-Credits-Charged": "1", "X-Credits-Remaining": "99",
                                 "X-Cache-Status": "HIT", "X-Request-Id": "req_1"})
        yt = self.client()
        data = yt.transcript("https://youtu.be/dQw4w9WgXcQ", language="de", metadata=True)

        self.assertEqual(data, body)
        self.assertEqual(segments(data)[0]["text"], "Hi")
        req = FakeAPI.requests[0]
        self.assertEqual(req["path"], "/api/v2/youtube/transcript")
        self.assertEqual(req["query"], {
            "video_url": "https://youtu.be/dQw4w9WgXcQ", "language": "de", "format": "json",
            "include_timestamp": "true", "send_metadata": "true",
        })
        self.assertEqual(req["headers"]["Authorization"], f"Bearer {KEY}")
        self.assertEqual(req["headers"]["User-Agent"], f"youtubetranscriptapi-python/{__version__}")
        info = yt.last_response
        self.assertEqual((info.credits_charged, info.credits_remaining, info.cache_status, info.request_id),
                         (1, 99, "HIT", "req_1"))

    def test_transcript_text(self):
        self.queue(200, {"video_id": "x", "language": "en", "transcript": "[0.0s] Hi\n[1.5s] there"})
        text = self.client().transcript_text("x", timestamps=True)
        self.assertEqual(text, "[0.0s] Hi\n[1.5s] there")
        self.assertEqual(FakeAPI.requests[0]["query"]["format"], "text")
        self.assertEqual(FakeAPI.requests[0]["query"]["include_timestamp"], "true")
        self.assertNotIn("send_metadata", FakeAPI.requests[0]["query"])

    def test_other_endpoints(self):
        yt = self.client()
        calls = [
            (lambda: yt.search("rust", type="channel", limit=5), "/youtube/search",
             {"q": "rust", "type": "channel", "limit": "5"}),
            (lambda: yt.search_channel("@TED", "ai"), "/youtube/channel/search",
             {"channel": "@TED", "q": "ai", "limit": "30"}),
            (lambda: yt.channel_videos("@TED"), "/youtube/channel/videos", {"channel": "@TED"}),
            (lambda: yt.latest_videos("@TED"), "/youtube/channel/latest", {"channel": "@TED"}),
            (lambda: yt.playlist_videos("PL1"), "/youtube/playlist/videos", {"playlist": "PL1"}),
            (lambda: yt.account(), "/account/whoami", {}),
        ]
        for call, path, query in calls:
            self.queue(200, {"results": []})
            call()
            req = FakeAPI.requests[-1]
            self.assertEqual(req["path"], "/api/v2" + path)
            self.assertEqual(req["query"], query)

    def test_resolve_channel_returns_id(self):
        self.queue(200, {"channel_id": "UCabc", "resolved_from": "@TED"})
        self.assertEqual(self.client().resolve_channel("@TED"), "UCabc")
        self.assertEqual(FakeAPI.requests[0]["query"], {"input": "@TED"})

    # ---- Errors -----------------------------------------------------------

    def test_404_raises_not_found(self):
        self.queue(404, {"detail": "No transcript for this video", "code": "transcript_not_found"},
                   **{"X-Request-Id": "req_404"})
        with self.assertRaises(NotFoundError) as cm:
            self.client().transcript("x")
        err = cm.exception
        self.assertEqual((err.status, err.code, err.message, err.request_id),
                         (404, "transcript_not_found", "No transcript for this video", "req_404"))
        self.assertEqual(len(FakeAPI.requests), 1)

    def test_402_exposes_action_url(self):
        detail = {"message": "This call needs 20 credits; you have 5.", "reason": "insufficient_credits",
                  "required": 20, "available": 5, "action_url": "https://example.test/billing",
                  "checkout_url": "https://example.test/checkout"}
        self.queue(402, {"detail": detail, "code": "insufficient_credits"})
        with self.assertRaises(InsufficientCreditsError) as cm:
            self.client().channel_videos("@TED")
        self.assertEqual(cm.exception.message, "This call needs 20 credits; you have 5.")
        self.assertEqual(cm.exception.action_url, "https://example.test/billing")
        self.assertEqual(cm.exception.checkout_url, "https://example.test/checkout")

    def test_401_is_not_retried(self):
        self.queue(401, {"detail": "Invalid API key", "code": "invalid_auth"})
        with self.assertRaises(AuthenticationError):
            self.client().transcript("x")
        self.assertEqual(len(FakeAPI.requests), 1)

    def test_429_is_retried_after_retry_after(self):
        self.queue(429, {"detail": "Slow down", "code": "rate_limited"}, **{"Retry-After": "0"})
        self.queue(200, {"video_id": "x", "language": "en", "transcript": []})
        data = self.client().transcript("x")
        self.assertEqual(data["video_id"], "x")
        self.assertEqual(len(FakeAPI.requests), 2)

    def test_retries_stop_at_max(self):
        for _ in range(3):
            self.queue(503, {"detail": "Upstream error", "code": "upstream_error"}, **{"Retry-After": "0"})
        with self.assertRaises(TransientError) as cm:
            self.client(max_retries=2).transcript("x")
        self.assertEqual(cm.exception.status, 503)
        self.assertEqual(len(FakeAPI.requests), 3)

    def test_429_without_retries(self):
        self.queue(429, {"detail": "Slow down", "code": "rate_limited"}, **{"Retry-After": "7"})
        with self.assertRaises(RateLimitError) as cm:
            self.client(max_retries=0).search("x")
        self.assertEqual(cm.exception.retry_after, 7.0)

    def test_non_json_error_body(self):
        self.queue(500, b"<html>Bad gateway</html>", **{"Retry-After": "0"})
        with self.assertRaises(TransientError) as cm:
            self.client(max_retries=0).transcript("x")
        self.assertEqual(cm.exception.message, "HTTP 500")

    def test_network_error_is_transient(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        yt = YouTubeTranscriptAPI(KEY, base_url=f"http://127.0.0.1:{port}", max_retries=0, timeout=2)
        with self.assertRaises(TransientError) as cm:
            yt.transcript("x")
        self.assertIsNone(cm.exception.status)

    # ---- Keys -------------------------------------------------------------

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthenticationError) as cm:
                YouTubeTranscriptAPI()
        self.assertIn("YTT_API_KEY", str(cm.exception))

    def test_key_from_env(self):
        with mock.patch.dict(os.environ, {"YT_API_KEY": "tk_live_env"}, clear=True):
            self.assertEqual(YouTubeTranscriptAPI().api_key, "tk_live_env")
        with mock.patch.dict(os.environ, {"YTT_API_KEY": "tk_live_a", "YT_API_KEY": "tk_live_b"}, clear=True):
            self.assertEqual(YouTubeTranscriptAPI().api_key, "tk_live_a")

    def test_repr_hides_key(self):
        self.assertNotIn(KEY, repr(self.client()))

    # ---- CLI --------------------------------------------------------------

    def run_cli(self, *args):
        """Runs the CLI with YTT_API_KEY set and every client pointed at the fake."""
        out, err = io.StringIO(), io.StringIO()
        original = YouTubeTranscriptAPI.__init__
        base = self.base

        def init(obj, api_key=None, **kw):
            kw.setdefault("base_url", base)
            original(obj, api_key, **kw)

        with mock.patch.dict(os.environ, {"YTT_API_KEY": KEY}, clear=True), \
                mock.patch.object(YouTubeTranscriptAPI, "__init__", init), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_cli_transcript_text(self):
        self.queue(200, {"video_id": "x", "language": "en", "transcript": "Hello there"})
        code, out, _ = self.run_cli("transcript", "x")
        self.assertEqual((code, out), (0, "Hello there\n"))

    def test_cli_out_of_credits(self):
        self.queue(402, {"detail": {"message": "Out of credits.", "action_url": "https://example.test/b"},
                         "code": "insufficient_credits"})
        code, _, err = self.run_cli("search", "rust")
        self.assertEqual(code, 2)
        self.assertIn("https://example.test/b", err)


if __name__ == "__main__":
    unittest.main()
