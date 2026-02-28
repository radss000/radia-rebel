#!/usr/bin/env python3
"""Refresh yt-dlp cookies by extracting them from a local browser."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from yt_dlp.cookies import YoutubeDLCookieJar, extract_cookies_from_browser


def _parse_output_path(raw: str | None) -> Path:
    if raw:
        return Path(raw)
    default_path = Path("music-pipeline") / "secrets" / "youtube_cookies.txt"
    return default_path


def refresh_cookies(*, browser: str, profile: str | None, container: str | None, output_path: Path) -> None:
    cookie_jar = extract_cookies_from_browser(browser, profile=profile, container=container)
    if not isinstance(cookie_jar, YoutubeDLCookieJar):
        wrapped = YoutubeDLCookieJar()
        for cookie in cookie_jar:
            wrapped.set_cookie(cookie)
        cookie_jar = wrapped

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cookie_jar.save(str(output_path))
    try:
        os.chmod(output_path, 0o600)
    except PermissionError:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract browser cookies for yt-dlp.")
    parser.add_argument("--browser", default="chrome", help="Browser name (chrome, chromium, brave, edge, firefox, safari)")
    parser.add_argument("--profile", default=None, help="Browser profile name or path")
    parser.add_argument("--container", default=None, help="Firefox container name (optional)")
    parser.add_argument("--output", default=None, help="Output cookies path (default: music-pipeline/secrets/youtube_cookies.txt)")
    args = parser.parse_args()

    output_path = _parse_output_path(args.output)
    refresh_cookies(browser=args.browser, profile=args.profile, container=args.container, output_path=output_path)
    print(f"Wrote cookies to {output_path}")


if __name__ == "__main__":
    main()
