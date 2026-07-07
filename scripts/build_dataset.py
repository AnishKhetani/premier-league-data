#!/usr/bin/env python3
"""Clean + combine the raw football-data.co.uk season CSVs into two tables.

Outputs (to ``data/processed/`` as both CSV and Parquet):

* ``results``            - core match results, standardized across all eras.
* ``results_with_odds``  - the same match key columns plus every bookmaker odds
                           column, kept intact and renamed clearly by bookmaker.

Raw files are read with Python's ``csv.reader`` (not pandas) because some season
files have ragged/malformed rows that break pandas' default parser. See SPEC.md
for the full list of parsing gotchas and how they're handled.
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"
# Parquet is also copied here so the installed package ships the data.
PKG_DATA_DIR = ROOT / "src" / "premier_league_data" / "data"

# Core (non-odds) source columns we standardize, mapped to output names.
CORE_MAP = {
    "Date": "date",
    "HomeTeam": "home_team",
    "AwayTeam": "away_team",
    "FTHG": "fthg",
    "FTAG": "ftag",
    "FTR": "ftr",
    "HTHG": "hthg",
    "HTAG": "htag",
    "HTR": "htr",
    "Referee": "referee",
}
# Non-odds columns that exist in the raw files but we don't carry into either
# table: identifiers we replace, and match-statistics (shots, corners, fouls,
# cards, woodwork, offsides, booking points) which are out of scope here -- this
# package is about results + bookmaker odds, not in-play match stats.
DROP_COLS = {
    "Div", "Time", "Attendance",
    "HS", "AS", "HST", "AST", "HHW", "AHW", "HC", "AC", "HF", "AF",
    "HO", "AO", "HY", "AY", "HR", "AR", "HBP", "ABP",
}

# --- bookmaker code -> readable name (per football-data's notes) -------------
BOOKS = {
    "B365": "bet365",
    "BFD": "betfair_sb",
    "BMGM": "betmgm",
    "BFE": "betfair_ex",
    "BV": "betvictor",
    "BW": "bwin",
    "BS": "bluesquare",
    "CL": "coral",
    "GB": "gamebookers",
    "IW": "interwetten",
    "LB": "ladbrokes",
    "PS": "pinnacle",
    "P": "pinnacle",
    "SB": "sportingbet",
    "SO": "sportingodds",
    "SJ": "stanjames",
    "SY": "stanleybet",
    "VC": "vcbet",
    "WH": "williamhill",
    "BF": "betfair",
    "1XB": "onexbet",
    "Max": "market_max",
    "Avg": "market_avg",
    "BbMx": "betbrain_max",
    "BbAv": "betbrain_avg",
}
# market suffix -> readable market name
MARKETS = {
    "H": "1x2_home",
    "D": "1x2_draw",
    "A": "1x2_away",
    ">2.5": "over25",
    "<2.5": "under25",
    "AHH": "ah_home",
    "AHA": "ah_away",
    "AH": "ah_line",  # per-book handicap line, e.g. B365AH / GBAH / LBAH
}


def build_odds_rename() -> dict[str, str]:
    """Generate the football-data -> readable rename map for odds columns.

    football-data names odds columns ``{book}[C]{market}`` where an infix ``C``
    denotes closing odds. We enumerate every book x market combination; only the
    columns actually present in the data end up being renamed.
    """
    rename: dict[str, str] = {}
    for bcode, bname in BOOKS.items():
        for msuf, mname in MARKETS.items():
            rename[f"{bcode}{msuf}"] = f"{bname}_{mname}"
            rename[f"{bcode}C{msuf}"] = f"{bname}_{mname}_close"
    # market-level Asian-handicap lines (not tied to a single bookmaker)
    rename["AHh"] = "ah_line"
    rename["AHCh"] = "ah_line_close"
    rename["BbAHh"] = "ah_line_betbrain"
    return rename


ODDS_RENAME = build_odds_rename()


# --- parsing helpers ---------------------------------------------------------
def season_label(code: str) -> str:
    """'9394' -> '1993-94', '2526' -> '2025-26'."""
    start2 = int(code[:2])
    # football-data codes: 93..99 => 1993..1999, 00..25 => 2000..2025
    start_year = 1900 + start2 if start2 >= 93 else 2000 + start2
    return f"{start_year}-{code[2:]}"


def season_start_year(code: str) -> int:
    start2 = int(code[:2])
    return 1900 + start2 if start2 >= 93 else 2000 + start2


def resolve_date(raw: str, start_year: int):
    """Parse a dd/mm/yy or dd/mm/yyyy date, resolving 2-digit years via season.

    A PL season runs Aug (start_year) .. May (start_year+1): months 7-12 belong
    to the start year, months 1-6 to start_year + 1.
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$", raw)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
    if len(year) == 4:
        full_year = int(year)
    else:
        # resolve the ambiguous 2-digit year from the season, not the year alone
        full_year = start_year if month >= 7 else start_year + 1
    try:
        return pd.Timestamp(year=full_year, month=month, day=day).date()
    except ValueError:
        return None


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def normalize_header(header: list[str]) -> list[str]:
    """Strip BOM/whitespace; leave names otherwise as-is."""
    out = []
    for i, col in enumerate(header):
        col = (col or "").strip()
        if i == 0:
            col = col.lstrip("﻿")
        out.append(col)
    return out


def read_season(path: Path) -> list[dict]:
    """Read one raw season CSV into a list of dict rows (by-position mapping)."""
    code = path.stem.split("_")[-1]  # E0_9394 -> 9394
    start_year = season_start_year(code)
    label = season_label(code)

    # football-data files are inconsistently encoded: recent ones are UTF-8 with
    # a BOM, older ones are cp1252 (e.g. 0xa0 non-breaking space). Try UTF-8
    # first, fall back to cp1252 which decodes any byte.
    data = path.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252")

    reader = csv.reader(io.StringIO(text))
    try:
        header = normalize_header(next(reader))
    except StopIteration:
        return []
    width = len(header)

    rows = []
    for raw_row in reader:
        # skip blank / all-empty rows
        if not any(cell.strip() for cell in raw_row):
            continue
        # pad short rows, truncate long ones -> align to header by position
        if len(raw_row) < width:
            raw_row = raw_row + [""] * (width - len(raw_row))
        elif len(raw_row) > width:
            raw_row = raw_row[:width]
        rec = dict(zip(header, raw_row))

        date = resolve_date(rec.get("Date", ""), start_year)
        home = (rec.get("HomeTeam", "") or "").strip()
        away = (rec.get("AwayTeam", "") or "").strip()
        fthg = to_int(rec.get("FTHG"))
        ftag = to_int(rec.get("FTAG"))
        # drop rows whose core fields don't parse (header repeats, junk rows)
        if date is None or not home or not away or fthg is None or ftag is None:
            continue

        out = {
            "match_id": f"{code}-{slug(home)}-{slug(away)}",
            "season": label,
            "season_code": code,
            "date": date,
            "home_team": home,
            "away_team": away,
            "fthg": fthg,
            "ftag": ftag,
            "ftr": (rec.get("FTR", "") or "").strip() or None,
            "hthg": to_int(rec.get("HTHG")),
            "htag": to_int(rec.get("HTAG")),
            "htr": (rec.get("HTR", "") or "").strip() or None,
            "referee": (rec.get("Referee", "") or "").strip() or None,
        }
        # carry every odds column through, renamed
        for src, val in rec.items():
            if src in CORE_MAP or src in DROP_COLS or src == "":
                continue
            val = (val or "").strip()
            if val == "":
                continue
            out_col = ODDS_RENAME.get(src, src)  # keep unknown cols intact
            out[out_col] = to_float(val)
        rows.append(out)
    return rows


def to_int(val):
    val = (val or "").strip() if isinstance(val, str) else val
    if val in (None, ""):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def to_float(val):
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# --- main --------------------------------------------------------------------
CORE_COLUMNS = [
    "match_id", "season", "season_code", "date",
    "home_team", "away_team", "fthg", "ftag", "ftr",
    "hthg", "htag", "htr", "referee",
]
ODDS_KEY_COLUMNS = ["match_id", "season", "date", "home_team", "away_team"]


def main() -> int:
    files = sorted(RAW_DIR.glob("E0_*.csv"))
    if not files:
        print(
            f"No raw files found in {RAW_DIR}. Run scripts/fetch_data.py first.",
            file=sys.stderr,
        )
        return 1

    all_rows: list[dict] = []
    for path in files:
        rows = read_season(path)
        print(f"  {path.name}: {len(rows)} matches")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["date", "home_team"]).reset_index(drop=True)

    # nullable integer goal columns
    for col in ("fthg", "ftag", "hthg", "htag"):
        df[col] = df[col].astype("Int64")

    # --- table 1: core results ---
    results = df[CORE_COLUMNS].copy()

    # --- table 2: results + odds ---
    odds_cols = [c for c in df.columns if c not in CORE_COLUMNS]
    results_with_odds = df[ODDS_KEY_COLUMNS + odds_cols].copy()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_table(results, "results")
    write_table(results_with_odds, "results_with_odds")

    run_sanity_checks(results)

    print("\nRow counts:")
    print(f"  results            : {len(results):>6} rows, {results.shape[1]} cols")
    print(
        f"  results_with_odds  : {len(results_with_odds):>6} rows, "
        f"{results_with_odds.shape[1]} cols "
        f"({len(odds_cols)} odds columns)"
    )
    return 0


def write_table(frame: pd.DataFrame, name: str) -> None:
    frame.to_csv(OUT_DIR / f"{name}.csv", index=False)
    frame.to_parquet(OUT_DIR / f"{name}.parquet", index=False)
    # keep the packaged (pip-installable) copy in sync with the canonical output
    PKG_DATA_DIR.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(PKG_DATA_DIR / f"{name}.parquet", index=False)


def run_sanity_checks(results: pd.DataFrame) -> None:
    n = len(results)
    assert n >= 12_700, f"expected >= 12,700 matches, got {n}"

    dupes = results["match_id"].duplicated().sum()
    assert dupes == 0, f"found {dupes} duplicate match_id(s)"

    dmin, dmax = results["date"].min(), results["date"].max()
    lo, hi = pd.Timestamp("1993-01-01"), pd.Timestamp("2027-01-01")
    assert lo <= dmin and dmax <= hi, f"dates out of range: {dmin} .. {dmax}"

    print(
        f"\nSanity checks passed: {n} matches, 0 duplicate ids, "
        f"dates {dmin.date()} .. {dmax.date()}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
