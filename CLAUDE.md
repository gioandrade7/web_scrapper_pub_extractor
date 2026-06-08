# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Research pipeline (IComp/UFAM × JusBrasil) for semantic segmentation of Brazilian federal gazette (Diário Oficial da União — DOU) publications. Three sequential, independently runnable modules:

```
scraper/ → text_extraction/ → semantic_seg/
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY
# ChromeDriver must match installed Chrome version
```

Key `.env` variable: `OPENAI_API_KEY` (required for `semantic_seg/` only).

## Running Each Module

**Module 1 — Scraper** (edit `url` in `main()` before running):
```bash
cd scraper/
python pub_scrapper.py
```
Output: `scraper/pubs_extracted/dou_secX_DD-MM/Pub_N.txt`

**Module 2a — PDF → Markdown:**
```bash
cd text_extraction/
python pdf_extract.py -i arquivo.pdf -o saida/

# Parallel processing
python pdf_extract.py -i arquivo.pdf -o saida/ --workers 8

# Reprocess from scratch (ignore resume)
python pdf_extract.py -i arquivo.pdf -o saida/ --no-resume
```
Output: `saida/page_NNNN.md` per page and `saida/documento_final.md`. Resumes automatically (skips already-processed pages).

**Module 2b — RTF → Text** (edit `ano`/`rtf_path` variables at top of file):
```bash
cd text_extraction/
python rtf_txt.py
```

**Module 3 — Semantic Segmentation:**
```bash
cd semantic_seg/
python main.py \
    --config configs/dou_sec1.json \
    --diretorio ../text_extraction/out/dou_sec1_06-01 \
    --saida resultados/dou_sec1_06-01.json \
    --model gpt-4o \
    --janela-paginas 10
```

**Batch run all DOU documents:**
```bash
cd semantic_seg/
python run_all_dou.py --filtro sec1 --model gpt-4o
python run_all_dou.py --dry-run   # preview without API calls
```

**Evaluate segmentation results:**
```bash
cd semantic_seg/
python avaliar.py \
    --resultado resultados/dou_sec1_06-01.json \
    --anotacoes ../scraper/pubs_extracted/dou_sec1_06-01 \
    --threshold 0.5 \
    --relatorio resultados/dou_sec1_06-01_relatorio.json

# For legal documents dataset:
python avaliar.py --formato lei --resultado ... --anotacoes ./dataset3txtLEI/...
```

## Architecture

### scraper/
- `pub_scrapper.py`: One Selenium driver collects all publication links + session cookies, then `httpx` async client (up to 20 concurrent) downloads all publications. Persistent 403s fall back to a pool of 3 Selenium drivers.
- `dou_html_parser.py`: Parses `<div class="texto-dou">` HTML, extracts text from `<p>` tags only (tables are not captured — known limitation).

### text_extraction/
- `pdf_extract.py`: Reads the native text layer from PDFs directly — no OCR, no ML models, no API calls. Three extraction strategies selected at import time: (1) **pymupdf4llm** (preferred, auto column/table detection → Markdown), (2) **PyMuPDF blocks + column sort** (fallback, heuristic multi-column reordering), (3) **plain `get_text()`** (last resort). Supports parallel extraction via `ProcessPoolExecutor` (`--workers N`). Warns on pages returning fewer than 100 chars (likely scanned). Can also be used as a library: `from text_extraction.pdf_extract import extract_pdf`.
- `rtf_txt.py`: Converts legacy RTF law files to plain text via `striprtf`.

### semantic_seg/
- `main.py`: CLI entry point; wires config, pages, and pipeline together.
- `utils_llm.py`: Core sliding-window pipeline. Builds `texto_completo` once with `<!-- PÁGINA N -->` markers; advances a char-position pointer (`pos_atual`) after each identified block using `offset_fim` anchors. Auto-expands the window (up to 2×) if a block appears truncated. Tolerant anchor matching (`_localizar_ancora`) handles markdown noise, whitespace, accent, and case variations across 4 fallback layers.
- `utils_files.py`: Loads paginated `.md` files sorted by filename; assembles the full text string; handles mid-page window slicing by re-injecting the page marker header.
- `avaliar.py`: Greedy matching (highest `word_f1` first) of predicted blocks against reference files. Reports Precision/Recall/F1 for detection, plus average `word_f1`/`char_f1` for text quality. Supports both DOU format (`Pub_N.txt`) and legal document format (`{seq}-{class}-{pag}-{pag}.txt`) with per-class classification metrics.

### Config files (semantic_seg/)
`pub.yaml` / `pub2.yaml` / `lei.yaml` define the document type, block definition, granularity rules, and segment categories injected into the LLM prompt. The prompt template in `utils_llm.py:construir_prompt()` is generic; all document-specific rules live in these config files.

## Known Limitations
- Scraper misses HTML tables (only `<p>` tags extracted).
- `pdf_extract.py` requires a native text layer; scanned/image-only PDFs need OCR (pages under 100 chars trigger a warning).
- Segmentation config JSON/YAML must be tailored per document type.
