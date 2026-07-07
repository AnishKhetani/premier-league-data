#!/usr/bin/env python3
"""Fetch every Premier League (E0) season CSV from football-data.co.uk.

Downloads all 33 published seasons (1993-94 .. 2025-26) into ``data/raw/``.
Files are cached: an existing, non-empty raw file is skipped unless ``--force``
is passed. This keeps the repo light (raw files are gitignored) while making the
dataset fully reproducible from source.

Data source: https://www.football-data.co.uk/  (please credit them).
"""
from __future__ import annotations

import argparse
import datetime
import sys
import time
from pathlib import Path

import requests

# --- season codes -----------------------------------------------------------
FIRST_SEASON = 1993  # 1993-94 is the first season football-data publishes E0 for


def _latest_start_year() -> int:
    """Start year of the current season.

    football-data posts a new season's E0 file around August, so before then the
    "current" season is still last calendar year's. Floored at 2025 so the list
    never regresses below what's known to exist.
    """
    today = datetime.date.today()
    current = today.year if today.month >= 8 else today.year - 1
    return max(2025, current)


LAST_SEASON = _latest_start_year()  # e.g. 2025 -> 2025-26

BASE_URL = "https://www.football-data.co.uk/mmz4281/{code}/E0.csv"
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

# football-data occasionally 403s bare/unknown user agents; use a browser-like UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def season_code(start_year: int) -> str:
    """1993 -> '9394', 1999 -> '9900', 2000 -> '0001', 2025 -> '2526'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_codes() -> list[str]:
    return [season_code(y) for y in range(FIRST_SEASON, LAST_SEASON + 1)]


def fetch_one(code: str, dest: Path, force: bool, session: requests.Session) -> str:
    """Return one of: 'cached', 'downloaded', 'failed'."""
    if dest.exists() and dest.stat().st_size > 0 and not force:
        return "cached"
    url = BASE_URL.format(code=code)
    try:
        resp = session.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:  # network / HTTP error
        print(f"  ! {code}: {exc}", file=sys.stderr)
        return "failed"
    if not resp.content.strip():
        print(f"  ! {code}: empty response", file=sys.stderr)
        return "failed"
    dest.write_bytes(resp.content)
    return "downloaded"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-download even if cached"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="only (re)fetch the current season -- used by the weekly refresh CI",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    codes = season_codes()
    if args.latest:
        codes = codes[-1:]  # just the current season
        args.force = True   # its file changes as matches are played
    print(f"Fetching {len(codes)} Premier League season file(s) -> {RAW_DIR}")

    counts = {"cached": 0, "downloaded": 0, "failed": 0}
    with requests.Session() as session:
        for code in codes:
            dest = RAW_DIR / f"E0_{code}.csv"
            status = fetch_one(code, dest, args.force, session)
            counts[status] += 1
            print(f"  {code}: {status}")
            if status == "downloaded":
                time.sleep(0.5)  # be polite to the host

    print(
        f"\nDone. downloaded={counts['downloaded']} "
        f"cached={counts['cached']} failed={counts['failed']}"
    )
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
