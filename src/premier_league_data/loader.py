"""Loader API for the Premier League results + odds dataset.

The dataset ships as two Parquet tables bundled inside the package, so
``load_results()`` and ``load_results_with_odds()`` work immediately after
``pip install`` — no download step required. Regenerate the tables from source
with ``scripts/fetch_data.py`` + ``scripts/build_dataset.py`` (see SPEC.md).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

__all__ = ["load_results", "load_results_with_odds", "available_seasons", "data_path"]

_FILENAMES = {
    "results": "results.parquet",
    "results_with_odds": "results_with_odds.parquet",
}


def data_path(table: str) -> Path:
    """Return the on-disk path to a bundled Parquet table.

    Looks first for data bundled inside the installed package, then falls back
    to the repository's ``data/processed/`` directory (useful when working from
    a source checkout before the package data has been refreshed).

    Args:
        table: Either ``"results"`` or ``"results_with_odds"``.

    Returns:
        Path to the Parquet file for ``table``.

    Raises:
        ValueError: If ``table`` is not a known table name.
        FileNotFoundError: If the Parquet file cannot be located.
    """
    try:
        filename = _FILENAMES[table]
    except KeyError:
        raise ValueError(
            f"unknown table {table!r}; expected one of {sorted(_FILENAMES)}"
        ) from None

    # 1) bundled package data (the normal installed case)
    bundled = Path(__file__).resolve().parent / "data" / filename
    if bundled.is_file():
        return bundled

    # 2) source-checkout fallback: <repo>/data/processed/
    repo_processed = (
        Path(__file__).resolve().parents[2] / "data" / "processed" / filename
    )
    if repo_processed.is_file():
        return repo_processed

    raise FileNotFoundError(
        f"could not find {filename}. If working from a source checkout, run "
        "scripts/fetch_data.py then scripts/build_dataset.py first."
    )


def load_results(season: str | None = None) -> pd.DataFrame:
    """Load the core Premier League results table.

    One row per match, standardized across every season from 1993-94 onward:
    ``match_id``, ``season``, ``season_code``, ``date``, ``home_team``,
    ``away_team``, ``fthg``, ``ftag``, ``ftr``, ``hthg``, ``htag``, ``htr``,
    ``referee``. See SPEC.md for the full schema.

    Args:
        season: Optional season label to filter to, e.g. ``"2023-24"``. If
            ``None`` (default), all seasons are returned.

    Returns:
        A pandas DataFrame sorted by date, with ``date`` as ``datetime64`` and
        goal columns as nullable integers.
    """
    df = pd.read_parquet(data_path("results"))
    return _filter_season(df, season)


def load_results_with_odds(season: str | None = None) -> pd.DataFrame:
    """Load results joined with every bookmaker odds column.

    Same match-identity key columns as :func:`load_results` (``match_id``,
    ``season``, ``date``, ``home_team``, ``away_team``) plus all betting-odds
    columns football-data.co.uk provides, renamed clearly by bookmaker
    (e.g. ``bet365_1x2_home``, ``pinnacle_1x2_home_close``,
    ``market_avg_1x2_away``, ``bet365_over25``, ``bet365_ah_home``). Odds are
    sparse: a column is ``NaN`` for seasons where that bookmaker/market wasn't
    quoted. See SPEC.md for the naming grammar.

    Args:
        season: Optional season label to filter to, e.g. ``"2023-24"``. If
            ``None`` (default), all seasons are returned.

    Returns:
        A pandas DataFrame sorted by date.
    """
    df = pd.read_parquet(data_path("results_with_odds"))
    return _filter_season(df, season)


def available_seasons() -> list[str]:
    """Return the sorted list of season labels present in the dataset.

    Returns:
        Season labels like ``["1993-94", "1994-95", ..., "2025-26"]``.
    """
    seasons = load_results()["season"].unique().tolist()
    return sorted(seasons)


def _filter_season(df: pd.DataFrame, season: str | None) -> pd.DataFrame:
    if season is None:
        return df
    filtered = df[df["season"] == season]
    if filtered.empty:
        raise ValueError(
            f"no matches for season {season!r}; "
            f"available: {sorted(df['season'].unique())}"
        )
    return filtered.reset_index(drop=True)
