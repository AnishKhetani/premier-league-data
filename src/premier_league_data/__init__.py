"""premier-league-data — open Premier League results + bookmaker odds dataset.

Data sourced from football-data.co.uk (please credit them). Pipeline code is
MIT licensed; no license is claimed over the underlying data.
"""
from __future__ import annotations

from .loader import (
    available_seasons,
    data_path,
    load_results,
    load_results_with_odds,
)

__version__ = "0.1.0"

__all__ = [
    "load_results",
    "load_results_with_odds",
    "available_seasons",
    "data_path",
    "__version__",
]
