"""
Batch-runs pub_scrapper.py for the 10 new Section 1 DOU dates.
"""

import subprocess
import sys
from pathlib import Path

DATES = [
    "08-01-2025",
    "16-01-2025",
    "18-02-2025",
    "06-03-2025",
    "11-03-2025",
    "04-04-2025",
    "23-01-2026",
    "04-02-2026",
    "03-03-2026",
    "05-03-2026",
]

SCRAPER = Path(__file__).parent / "pub_scrapper.py"


def main():
    for date in DATES:
        url = f"https://in.gov.br/leiturajornal?data={date}&secao=do1"
        print(f"\n{'='*60}")
        print(f"Scraping: {url}")
        print('='*60)
        result = subprocess.run(
            [sys.executable, str(SCRAPER), "--url", url],
            cwd=str(SCRAPER.parent),
        )
        if result.returncode != 0:
            print(f"[ERROR] Scraper failed for {date} (exit {result.returncode})")


if __name__ == "__main__":
    main()
