# Data provenance & licensing

**The MIT license (`LICENSE`) covers the pipeline code in this repository only —
not the underlying data.**

## Where the data comes from

All match results and betting odds in this dataset are downloaded from
**[football-data.co.uk](https://www.football-data.co.uk/)**, which publishes free
historical football results and odds. This project merely fetches, cleans, and
reshapes those files; it does not create the underlying data.

## What this project does and doesn't claim

- This project **claims no ownership or license over the data itself.**
  football-data.co.uk does not state explicit redistribution terms, so we make no
  representation about your right to redistribute it.
- The processed tables and any bundled copies are provided **as a convenience**,
  and can be **regenerated from source** at any time with the scripts in this
  repo (`scripts/fetch_data.py` + `scripts/build_dataset.py`).
- If you use this data, **credit football-data.co.uk** and review their site for
  any terms before redistributing.

## If you are football-data.co.uk

Thank you for maintaining a genuinely useful public resource. If you'd prefer we
not bundle processed copies of your data in this repository, please open an issue
and we'll switch to a fetch-only distribution (code only, data generated locally).
