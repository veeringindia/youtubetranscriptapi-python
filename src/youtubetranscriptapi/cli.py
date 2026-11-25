"""Command line: ``youtubetranscriptapi transcript <video>`` and friends."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from ._client import YouTubeTranscriptAPI
from ._errors import InsufficientCreditsError, YouTubeTranscriptAPIError
from ._version import __version__


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="youtubetranscriptapi",
        description="YouTube transcripts, search and channel and playlist listings from YouTubeTranscriptAPI. "
        "Reads your key from YTT_API_KEY.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--api-key", help="API key (default: $YTT_API_KEY)")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    t = sub.add_parser("transcript", help="a video's transcript (1 credit)")
    t.add_argument("video", help="video ID or URL")
    t.add_argument("--language", "-l", default="en")
    t.add_argument("--json", action="store_true", help="print JSON segments instead of plain text")
    t.add_argument("--timestamps", "-t", action="store_true", help="prefix lines with [12.3s]")
    t.add_argument("--metadata", action="store_true", help="with --json: include title, author, thumbnail")

    s = sub.add_parser("search", help="search YouTube (4 credits)")
    s.add_argument("query")
    s.add_argument("--type", choices=["video", "channel"], default="video")
    s.add_argument("--limit", type=int, default=20)

    cs = sub.add_parser("channel-search", help="search one channel's videos (1 credit)")
    cs.add_argument("channel", help="@handle, URL or UC… ID")
    cs.add_argument("query")
    cs.add_argument("--limit", type=int, default=30)

    cv = sub.add_parser("channel-videos", help="a channel's latest uploads, up to 100 (20 credits)")
    cv.add_argument("channel")

    cl = sub.add_parser("latest", help="a channel's 15 newest uploads (free)")
    cl.add_argument("channel")

    r = sub.add_parser("resolve", help="@handle or URL to channel ID (free)")
    r.add_argument("channel")

    pl = sub.add_parser("playlist", help="videos in a playlist, up to 100 (20 credits)")
    pl.add_argument("playlist", help="playlist ID or URL")

    sub.add_parser("account", help="your plan and credit balance (free)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        yt = YouTubeTranscriptAPI(api_key=args.api_key)
        cmd = args.command
        if cmd == "transcript":
            if args.json:
                _print_json(yt.transcript(args.video, language=args.language,
                                          timestamps=args.timestamps, metadata=args.metadata))
            else:
                print(yt.transcript_text(args.video, language=args.language, timestamps=args.timestamps))
        elif cmd == "search":
            _print_json(yt.search(args.query, type=args.type, limit=args.limit))
        elif cmd == "channel-search":
            _print_json(yt.search_channel(args.channel, args.query, limit=args.limit))
        elif cmd == "channel-videos":
            _print_json(yt.channel_videos(args.channel))
        elif cmd == "latest":
            _print_json(yt.latest_videos(args.channel))
        elif cmd == "resolve":
            print(yt.resolve_channel(args.channel))
        elif cmd == "playlist":
            _print_json(yt.playlist_videos(args.playlist))
        elif cmd == "account":
            _print_json(yt.account())
    except InsufficientCreditsError as e:
        print(f"error: {e.message}", file=sys.stderr)
        if e.action_url:
            print(f"Fix it here: {e.action_url}", file=sys.stderr)
        return 2
    except YouTubeTranscriptAPIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
