# SPEC — premier-league-data

An open-source, pip-installable dataset of English **Premier League** match
results (top flight, division code `E0`), covering every season published by
football-data.co.uk. The package ships a reproducible pipeline (fetch → clean →
combine) and a small loader API, so anyone can regenerate the data from source
with one command.

## Data source

All data is downloaded from **football-data.co.uk**, which publishes one CSV per
season at:

```text
https://www.football-data.co.uk/mmz4281/{code}/E0.csv
```

`{code}` is the season written as two two-digit years, e.g.:

| Season   | code   |
|----------|--------|
| 1993-94  | `9394` |
| 1999-00  | `9900` |
| 2000-01  | `0001` |
| 2025-26  | `2526` |

**33 seasons** are available: **1993-94 through 2025-26**. Note that 1992-93 (the
inaugural Premier League season) is *not* published on football-data.co.uk and is
therefore out of scope.

The current season (`2526`) grows as matches are played, so row counts increase
over time.

## Licensing

- The **pipeline code** in this repository is licensed **MIT** (see `LICENSE`).
- football-data.co.uk does **not** state explicit redistribution terms for the
  underlying CSVs. This project therefore makes **no license claim over the data
  itself**. We credit and link football-data.co.uk prominently (README + a
  dedicated data-provenance section), and we keep raw per-season files out of the
  repo (regenerated on demand via the fetch script) rather than treating the
  source as a footnote.

If you use the data, credit **football-data.co.uk**.

## Output tables

The pipeline produces **two** tables, each written as **CSV and Parquet** to
`data/processed/`:

### 1. `results` — core match results

Standardized column names across all eras, with dates resolved to full
`YYYY-MM-DD`.

| column       | type   | notes                                             |
|--------------|--------|---------------------------------------------------|
| `match_id`   | str    | stable unique id: `{code}-{home_slug}-{away_slug}`|
| `season`     | str    | e.g. `1993-94`                                    |
| `season_code`| str    | e.g. `9394`                                        |
| `date`       | date   | resolved to full year (see gotchas)               |
| `home_team`  | str    |                                                   |
| `away_team`  | str    |                                                   |
| `fthg`       | Int    | full-time home goals                              |
| `ftag`       | Int    | full-time away goals                              |
| `ftr`        | str    | full-time result: `H` / `D` / `A`                 |
| `hthg`       | Int    | half-time home goals (NaN pre-1995-96)            |
| `htag`       | Int    | half-time away goals (NaN pre-1995-96)            |
| `htr`        | str    | half-time result (NaN pre-1995-96)                |
| `referee`    | str    | NaN before referees were recorded (~2000-01)      |

### 2. `results_with_odds` — results + all bookmaker odds

The same match-identity key columns (`match_id`, `season`, `date`, `home_team`,
`away_team`) plus **every betting-odds column football-data provides, kept intact
and renamed clearly by bookmaker**. This is the real differentiator versus most
public "PL results" datasets and is what makes closing-line-style analysis
possible.

Odds columns follow football-data's `{book}[C]{market}` grammar and are renamed
`{bookmaker}_{market}[_close]`, e.g.:

| football-data | renamed                     |
|---------------|-----------------------------|
| `B365H`       | `bet365_1x2_home`           |
| `B365D`       | `bet365_1x2_draw`           |
| `B365A`       | `bet365_1x2_away`           |
| `B365CH`      | `bet365_1x2_home_close`     |
| `PSH`         | `pinnacle_1x2_home`         |
| `B365>2.5`    | `bet365_over25`             |
| `B365C<2.5`   | `bet365_under25_close`      |
| `AHh`         | `ah_line`                   |
| `B365AHH`     | `bet365_ah_home`            |
| `MaxH`        | `market_max_1x2_home`       |
| `AvgA`        | `market_avg_1x2_away`       |

Bookmaker codes are mapped per football-data's own notes (Bet365, Bet&Win/bwin,
Interwetten, Ladbrokes, Pinnacle, William Hill, VC Bet, Betfair, BetVictor,
Coral, BetMGM, Gamebookers, Stan James, Sportingbet, Blue Square, 1xBet, …). The `C`
infix denotes **closing** odds; `Max`/`Avg` (and older `BbMx`/`BbAv`) are the
market maximum/average. Columns that don't match the known grammar (e.g.
Betbrain price *counts* `BbAH`, `BbOU`, `Bb1X2`) are **kept with their original
name** — no odds column is discarded.

**Out of scope:** football-data's in-play match-statistics columns (shots,
shots on target, corners, fouls, cards, offsides, woodwork, booking points) are
*not* carried into either table. This package is about results + bookmaker odds;
a match-stats table could be added later without changing these two.

## Known parsing gotchas (and how we handle them)

1. **Ragged / malformed rows.** Some season files have rows that break pandas'
   default CSV reader (stray commas, trailing empty fields, blank lines). We read
   with Python's `csv.reader` and map each row to the header **by position**,
   padding short rows and truncating long ones, then drop rows whose core fields
   (date, teams, full-time goals) don't parse. Old files also carry many trailing
   empty columns — these are ignored.

2. **Ambiguous two-digit years.** Date columns use `dd/mm/yy` in older files and
   `dd/mm/yyyy` in recent ones. A raw two-digit year is ambiguous, so we resolve
   it **using the season code, not the year alone**: a Premier League season spans
   August (year *N*) to May (year *N+1*), so months **July–December** map to the
   season's start year and **January–June** map to start year **+ 1**.

3. **BOM + `Time` column.** Recent files begin with a UTF-8 BOM and add a `Time`
   column; both are handled transparently by the header-normalization step.

## Sanity checks

The build fails loudly unless:

- total matches **≥ 12,700** (grows as the current season progresses),
- **no duplicate `match_id`s**,
- all `date`s fall within **1993-01-01 … 2027-01-01**.

## Repo layout

```text
premier-league-data/
├── SPEC.md
├── scripts/
│   ├── fetch_data.py      # download all 33 season CSVs -> data/raw/
│   └── build_dataset.py   # clean + combine -> data/processed/ (CSV + Parquet)
└── data/
    ├── raw/               # per-season source CSVs (gitignored; regenerate)
    └── processed/         # results.{csv,parquet}, results_with_odds.{csv,parquet}
```
