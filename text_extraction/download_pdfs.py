"""
Download full-edition DOU Section 1 PDFs from pesquisa.in.gov.br.
Fetches each page individually and merges into one PDF using PyMuPDF.
"""

import sys
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import fitz  # PyMuPDF

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

JORNAL_SEC1 = "515"
BASE_URL = "https://pesquisa.in.gov.br/imprensa/servlet/INPDFViewer"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://in.gov.br/",
}
MAX_WORKERS = 8
RETRY = 3

# date → (DD/MM/YYYY, total_pages, output_filename)
EDITIONS = [
    ("08/01/2025", 86,  "dou_sec1_08-01.pdf"),
    ("16/01/2025", 98,  "dou_sec1_16-01.pdf"),
    ("18/02/2025", 79,  "dou_sec1_18-02.pdf"),
    ("06/03/2025", 59,  "dou_sec1_06-03.pdf"),
    ("11/03/2025", 97,  "dou_sec1_11-03.pdf"),
    ("04/04/2025", 94,  "dou_sec1_04-04.pdf"),
    ("23/01/2026", 77,  "dou_sec1_23-01.pdf"),
    ("04/02/2026", 88,  "dou_sec1_04-02.pdf"),
    ("03/03/2026", 83,  "dou_sec1_03-03.pdf"),
    ("05/03/2026", 93,  "dou_sec1_05-03.pdf"),
]

OUT_DIR = Path(__file__).parent / "data" / "pdf"


def fetch_page(client: httpx.Client, date: str, page: int) -> bytes | None:
    url = f"{BASE_URL}?jornal={JORNAL_SEC1}&pagina={page}&data={date}&captchafield=firstAccess"
    for attempt in range(1, RETRY + 1):
        try:
            resp = client.get(url, timeout=30)
            if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                return resp.content
            log.warning(f"Page {page} attempt {attempt}: HTTP {resp.status_code}")
        except Exception as e:
            log.warning(f"Page {page} attempt {attempt}: {e}")
        if attempt < RETRY:
            time.sleep(2 ** attempt)
    return None


def download_edition(date: str, total_pages: int, out_path: Path) -> bool:
    if out_path.exists():
        log.info(f"Already exists, skipping: {out_path.name}")
        return True

    log.info(f"Downloading {out_path.name} ({total_pages} pages)…")
    pages: dict[int, bytes] = {}

    with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(fetch_page, client, date, p): p for p in range(1, total_pages + 1)}
            for f in as_completed(futures):
                p = futures[f]
                data = f.result()
                if data:
                    pages[p] = data
                else:
                    log.error(f"Failed to download page {p} of {out_path.name}")

    if len(pages) < total_pages:
        log.error(f"Only got {len(pages)}/{total_pages} pages for {out_path.name}, aborting merge.")
        return False

    log.info(f"Merging {len(pages)} pages → {out_path.name}")
    merged = fitz.open()
    for p in range(1, total_pages + 1):
        with fitz.open(stream=pages[p], filetype="pdf") as doc:
            merged.insert_pdf(doc)
    merged.save(str(out_path))
    merged.close()
    log.info(f"Saved: {out_path}")
    return True


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for date, total, fname in EDITIONS:
        ok = download_edition(date, total, OUT_DIR / fname)
        results.append((fname, ok))

    print("\n── Summary ──")
    for fname, ok in results:
        print(f"  {'✓' if ok else '✗'}  {fname}")


if __name__ == "__main__":
    main()
