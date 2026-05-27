# EDGAR Monitor

SEC EDGAR filing monitor for ticker watchlists with SQLite deduplication and
Markdown alerts.

## What It Does

`edgar_monitor.py` checks a ticker watchlist against the SEC company ticker and
submissions feeds, filters for market-relevant filing types, records filings it
has already seen in SQLite, and writes a Markdown summary of newly discovered
filings.

The default filing watchlist is tuned for fast-moving corporate events:

- `8-K`
- `SC 13D`
- `SC 13G`
- `4`
- `S-1`
- `DEFA14A`

## Quick Start

This project uses only the Python standard library.

```bash
python3 edgar_monitor.py \
  --watchlist watchlist.json \
  --db data/edgar_seen.sqlite3 \
  --output feeds/edgar-latest.md
```

The watchlist format is intentionally small:

```json
{
  "tickers": ["MSFT", "AAPL", "NVDA"]
}
```

## Output

Each run creates or updates a Markdown report like:

```md
# EDGAR Latest Filings

Generated: 2026-02-12 21:18:49 UTC

Watch forms: 4, 8-K, DEFA14A, S-1, SC 13D, SC 13G

| Filing Date | Ticker | Company | Form | Description | Link |
|---|---|---|---|---|---|
```

The SQLite database prevents repeat alerts for filings that were already seen in
earlier runs.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Notes

- The monitor respects a configurable pause between SEC requests.
- Generated state is written under `data/` and `feeds/` by default.
- This is a lightweight research/monitoring utility, not investment advice.

