# YouTube Transcript API: official Python client

[![PyPI](https://img.shields.io/pypi/v/youtube-transcript-api-client)](https://pypi.org/project/youtube-transcript-api-client/)
[![Python](https://img.shields.io/pypi/pyversions/youtube-transcript-api-client)](https://pypi.org/project/youtube-transcript-api-client/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/veeringindia/youtubetranscriptapi-python/blob/main/LICENSE)

Get the transcript of any public YouTube video in Python, plus YouTube search and channel and playlist listings, through the hosted [YouTubeTranscriptAPI](https://youtubetranscriptapi.com/?ref=python-sdk). Requests go out from our servers, not yours, so you don't deal with YouTube's IP blocks, `429 Too Many Requests` errors or proxies.

```bash
pip install youtube-transcript-api-client
```

```python
from youtubetranscriptapi import YouTubeTranscriptAPI

yt = YouTubeTranscriptAPI()  # reads your key from YTT_API_KEY
print(yt.transcript_text("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
```

You need an API key: [create a free account](https://youtubetranscriptapi.com/signup?ref=python-sdk) for 100 credits, no card required. One transcript costs 1 credit, and failed calls are never charged.

No dependencies, Python 3.9+, fully typed. The package installs as `youtube-transcript-api-client` and imports as `youtubetranscriptapi`.

## Get a transcript

```python
from youtubetranscriptapi import YouTubeTranscriptAPI

yt = YouTubeTranscriptAPI(api_key="tk_live_...")  # or set YTT_API_KEY

data = yt.transcript("dQw4w9WgXcQ", language="en", metadata=True)
print(data["metadata"]["title"])
for seg in data["transcript"]:
    print(f'{seg["start"]:>7.2f}s  {seg["text"]}')
```

`video` accepts a video ID, a `youtube.com/watch?v=` URL or a `youtu.be` link. The result looks like this:

```json
{
  "video_id": "dQw4w9WgXcQ",
  "language": "en",
  "transcript": [
    { "text": "First caption line", "start": 0, "duration": 4.12 },
    { "text": "Second caption line", "start": 4.12, "duration": 3.85 }
  ],
  "metadata": { "title": "…", "author_name": "…", "author_url": "…", "thumbnail_url": "…" }
}
```

Just the text, as one string:

```python
text = yt.transcript_text("dQw4w9WgXcQ")                    # plain text
lines = yt.transcript_text("dQw4w9WgXcQ", timestamps=True)  # "[0.0s] First caption line\n..."
```

If a video has no track in the language you ask for, another one may come back; check `data["language"]`.

## Search, channels and playlists

```python
yt.search("python tutorial", limit=10)                 # videos (4 credits)
yt.search("ted talks", type="channel", limit=5)        # channels
yt.search_channel("@TED", "climate", limit=10)         # inside one channel (1 credit)
yt.channel_videos("@TED")                              # latest uploads, up to 100 (20 credits)
yt.latest_videos("@TED")                               # 15 newest uploads (free)
yt.resolve_channel("@TED")                             # "UCAuUUnT6oDeKwE6v1NGQxug" (free)
yt.playlist_videos("PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf")  # up to 100 videos (20 credits)
yt.account()                                           # plan and balance (free)
```

Transcripts for a whole playlist:

```python
playlist = yt.playlist_videos("https://www.youtube.com/playlist?list=PL...")
for video in playlist["results"]:
    text = yt.transcript_text(video["videoId"])
    print(video["title"], len(text.split()), "words")
```

## Credits and response headers

| Method | Credits |
| --- | --- |
| `transcript`, `transcript_text` | 1 |
| `search` | 4 |
| `search_channel` | 1 |
| `channel_videos`, `playlist_videos` | 20 |
| `latest_videos`, `resolve_channel`, `account` | free (needs at least 1 credit) |

Only successful calls are charged. After each call, `yt.last_response` holds the headers:

```python
yt.transcript("dQw4w9WgXcQ")
info = yt.last_response
info.credits_charged     # 1
info.credits_remaining   # 99
info.cache_status        # "HIT" if the transcript was already stored, else "MISS"
```

## Errors

Every error is a `YouTubeTranscriptAPIError` with `status`, `code`, `message` and `request_id`:

```python
from youtubetranscriptapi import (
    YouTubeTranscriptAPI, NotFoundError, InsufficientCreditsError, YouTubeTranscriptAPIError,
)

try:
    data = yt.transcript("dQw4w9WgXcQ")
except NotFoundError:
    print("No captions, or the video is private or removed")
except InsufficientCreditsError as e:
    print(e.message, "->", e.action_url)  # link to top up or pick a plan
except YouTubeTranscriptAPIError as e:
    print(e.status, e.code, e.message)
```

| Exception | Status | When |
| --- | --- | --- |
| `AuthenticationError` | 401 | Missing, invalid or revoked key |
| `InsufficientCreditsError` | 402 | Not enough credits; `action_url` fixes it |
| `PermissionDeniedError` | 403 | Account paused |
| `NotFoundError` | 404 | No captions; video, channel or playlist unavailable |
| `ValidationError` | 422 | A parameter is missing or invalid |
| `RateLimitError` | 429 | Too many requests |
| `TransientError` | 408, 5xx, network | Temporary; safe to retry |

The client retries 408, 429 and 5xx responses twice by default, waiting for `Retry-After`. Change it with `YouTubeTranscriptAPI(max_retries=0)`.

## Timeouts

A video fetched for the first time usually takes 10–30 seconds; a stored one returns in about a second. The default timeout is 60 seconds: `YouTubeTranscriptAPI(timeout=90)` to raise it. On serverless hosts, give the function itself enough run time too.

## Command line

```bash
export YTT_API_KEY=tk_live_...

youtubetranscriptapi transcript dQw4w9WgXcQ                 # plain text
youtubetranscriptapi transcript dQw4w9WgXcQ -t              # with [12.3s] timestamps
youtubetranscriptapi transcript dQw4w9WgXcQ --json > t.json
youtubetranscriptapi search "rust async" --limit 5
youtubetranscriptapi playlist "https://www.youtube.com/playlist?list=PL..."
youtubetranscriptapi latest @TED
youtubetranscriptapi account
```

`python -m youtubetranscriptapi` works too.

## Coming from the youtube-transcript-api library?

The open-source [`youtube-transcript-api`](https://github.com/jdepoix/youtube-transcript-api) library fetches transcripts from your own machine, so on servers and cloud hosts YouTube often answers with `RequestBlocked` or `IpBlocked` errors. This package is a separate project: a client for a hosted API that fetches the transcript for you. The segment shape is the same (`text`, `start`, `duration`):

```python
# Before (youtube-transcript-api)
from youtube_transcript_api import YouTubeTranscriptApi
segments = YouTubeTranscriptApi().fetch("dQw4w9WgXcQ").to_raw_data()

# After (youtubetranscriptapi)
from youtubetranscriptapi import YouTubeTranscriptAPI
segments = YouTubeTranscriptAPI().transcript("dQw4w9WgXcQ")["transcript"]
```

## Links

- [API reference](https://youtubetranscriptapi.com/docs/api?ref=python-sdk)
- [Python guide](https://youtubetranscriptapi.com/youtube-transcript-api-python?ref=python-sdk)
- [Hosted MCP server](https://youtubetranscriptapi.com/youtube-mcp-server?ref=python-sdk) for Claude, ChatGPT and other AI apps
- Support: hello@youtubetranscriptapi.com

MIT licensed.
