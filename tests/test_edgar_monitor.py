import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from edgar_monitor import EdgarMonitor, Filing


class EdgarMonitorTests(unittest.TestCase):
    def test_load_watchlist_dedupes_and_normalizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            watchlist = Path(tmp) / "watchlist.json"
            watchlist.write_text(json.dumps({"tickers": [" msft ", "MSFT", "aapl"]}), encoding="utf-8")

            monitor = EdgarMonitor(watchlist, Path(tmp) / "db.sqlite3", Path(tmp) / "out.md")
            self.assertEqual(monitor._load_watchlist(), ["MSFT", "AAPL"])

    def test_mark_if_new_only_first_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitor = EdgarMonitor(Path(tmp) / "watchlist.json", Path(tmp) / "db.sqlite3", Path(tmp) / "out.md")
            monitor._init_db()

            filing = Filing(
                ticker="MSFT",
                company="Microsoft Corp",
                cik="0000789019",
                form="8-K",
                filing_date="2025-01-01",
                accession_number="0000789019-25-000001",
                primary_document="doc.htm",
                description="test",
            )

            self.assertTrue(monitor._mark_if_new(filing))
            self.assertFalse(monitor._mark_if_new(filing))

            with sqlite3.connect(monitor.db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM seen_filings").fetchone()[0]
                self.assertEqual(count, 1)

    def test_write_markdown_no_new_filings(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "feeds" / "edgar-latest.md"
            monitor = EdgarMonitor(Path(tmp) / "watchlist.json", Path(tmp) / "db.sqlite3", output)
            monitor._write_markdown([])
            text = output.read_text(encoding="utf-8")
            self.assertIn("No new filings found", text)


if __name__ == "__main__":
    unittest.main()
