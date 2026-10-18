"""Isolated yt-dlp metadata extraction; parent owns timeout/cancellation.

Running an extractor without processing its result prevents yt-dlp from
following a tweet's external article as though it were the original tweet.
"""
import json
import sys

from yt_dlp import YoutubeDL


def extract_metadata(url: str) -> dict:
    with YoutubeDL({
        "skip_download": True, "ignore_no_formats_error": True,
        "noplaylist": True, "quiet": True, "no_warnings": True,
        "socket_timeout": 15, "retries": 1, "extractor_retries": 1,
        "cachedir": False,
    }) as downloader:
        return downloader.extract_info(url, download=False, process=False)


if __name__ == "__main__":
    try:
        info = extract_metadata(sys.argv[-1])
        # process=False precedes yt-dlp's normal extractor metadata decoration.
        if isinstance(info, dict):
            info["extractor_key"] = "Twitter"
        print(json.dumps(info, ensure_ascii=False))
    except Exception:
        sys.exit(1)  # Parent exposes an actionable error, not raw credential-bearing output.
