#!/usr/bin/env python3
"""Monitor SEC EDGAR filings for a ticker watchlist."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TARGET_FORMS = {"8-K", "SC 13D", "SC 13G", "4", "S-1", "DEFA14A"}
USER_AGENT = "Will Beeson EDGAR Monitor willbeeson@outlook.com"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"


@dataclass(frozen=True)
class Filing:
    ticker: str
    company: str
    cik: str
    form: str
    filing_date: str
    accession_number: str
    primary_document: str
    description: str

    @property
    def filing_url(self) -> str:
        accession_no_dashes = self.accession_number.replace("-", "")
        return (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(self.cik)}/{accession_no_dashes}/{self.primary_document}"
        )


class EdgarMonitor:
    def __init__(
        self,
        watchlist_path: Path,
        db_path: Path,
        output_path: Path,
        request_pause_seconds: float = 0.2,
    ) -> None:
        self.watchlist_path = watchlist_path
        self.db_path = db_path
        self.output_path = output_path
        self.request_pause_seconds = request_pause_seconds

    def run(self) -> list[Filing]:
        tickers = self._load_watchlist()
        self._init_db()
        ticker_map = self._fetch_ticker_map()

        new_filings: list[Filing] = []
        for ticker in tickers:
            company_info = ticker_map.get(ticker.upper())
            if not company_info:
                print(f"[WARN] No CIK found for ticker: {ticker}")
                continue

            cik, company_name = company_info
            filings = self._fetch_recent_filings(cik)
            for filing in filings:
                if filing["form"] not in TARGET_FORMS:
                    continue

                item = Filing(
                    ticker=ticker.upper(),
                    company=company_name,
                    cik=cik,
                    form=filing["form"],
                    filing_date=filing["filingDate"],
                    accession_number=filing["accessionNumber"],
                    primary_document=filing["primaryDocument"],
                    description=filing.get("primaryDocDescription", "") or "",
                )
                if self._mark_if_new(item):
                    new_filings.append(item)

            time.sleep(self.request_pause_seconds)

        self._write_markdown(new_filings)
        return sorted(new_filings, key=lambda f: (f.filing_date, f.ticker), reverse=True)

    def _get_json(self, url: str) -> dict:
        request = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

    def _load_watchlist(self) -> list[str]:
        with self.watchlist_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        tickers = data.get("tickers")
        if not isinstance(tickers, list) or not all(isinstance(t, str) for t in tickers):
            raise ValueError("watchlist.json must contain {'tickers': [..]} with string tickers")

        return list(dict.fromkeys(t.upper().strip() for t in tickers if t.strip()))

    def _fetch_ticker_map(self) -> dict[str, tuple[str, str]]:
        payload = self._get_json(COMPANY_TICKERS_URL)

        mapping: dict[str, tuple[str, str]] = {}
        for value in payload.values():
            ticker = value["ticker"].upper()
            cik = str(value["cik_str"]).zfill(10)
            title = value["title"]
            mapping[ticker] = (cik, title)

        return mapping

    def _fetch_recent_filings(self, cik: str) -> Iterable[dict[str, str]]:
        data = self._get_json(SUBMISSIONS_URL.format(cik=cik))
        recent = data.get("filings", {}).get("recent", {})
        if not recent:
            return []

        keys = [
            "accessionNumber",
            "filingDate",
            "form",
            "primaryDocument",
            "primaryDocDescription",
        ]
        count = min(len(recent.get(key, [])) for key in keys)
        return [{key: recent.get(key, [""] * count)[i] for key in keys} for i in range(count)]

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_filings (
                    accession_number TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    company TEXT NOT NULL,
                    form TEXT NOT NULL,
                    filing_date TEXT NOT NULL,
                    filing_url TEXT NOT NULL,
                    seen_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _mark_if_new(self, filing: Filing) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO seen_filings
                (accession_number, ticker, company, form, filing_date, filing_url, seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filing.accession_number,
                    filing.ticker,
                    filing.company,
                    filing.form,
                    filing.filing_date,
                    filing.filing_url,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return cursor.rowcount == 1

    def _write_markdown(self, new_filings: list[Filing]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            "# EDGAR Latest Filings",
            "",
            f"Generated: {now}",
            "",
            f"Watch forms: {', '.join(sorted(TARGET_FORMS))}",
            "",
        ]

        if not new_filings:
            lines.append("No new filings found for the current run.")
        else:
            lines.extend(
                [
                    "| Filing Date | Ticker | Company | Form | Description | Link |",
                    "|---|---|---|---|---|---|",
                ]
            )
            for filing in sorted(new_filings, key=lambda f: (f.filing_date, f.ticker), reverse=True):
                desc = filing.description.replace("|", "\\|") if filing.description else "-"
                lines.append(
                    "| "
                    f"{filing.filing_date} | {filing.ticker} | {filing.company} | {filing.form} | {desc} | "
                    f"[document]({filing.filing_url}) |"
                )

        self.output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor SEC EDGAR for selected filings")
    parser.add_argument("--watchlist", default="watchlist.json", type=Path)
    parser.add_argument("--db", default="data/edgar_seen.sqlite3", type=Path)
    parser.add_argument("--output", default="feeds/edgar-latest.md", type=Path)
    parser.add_argument("--pause", default=0.2, type=float, help="Pause between SEC requests")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor = EdgarMonitor(
        watchlist_path=args.watchlist,
        db_path=args.db,
        output_path=args.output,
        request_pause_seconds=args.pause,
    )
    new_filings = monitor.run()

    print(f"Watchlist entries: {len(monitor._load_watchlist())}")
    print(f"New filings discovered this run: {len(new_filings)}")
    for filing in new_filings[:25]:
        print(f"- {filing.filing_date} {filing.ticker} {filing.form} {filing.accession_number}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
