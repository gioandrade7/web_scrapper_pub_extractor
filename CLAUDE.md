# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Research pipeline (IComp/UFAM × JusBrasil) for semantic segmentation of Brazilian federal gazette (Diário Oficial da União — DOU) publications and of federal statutes. Two sequential, independently runnable modules:

```
text_extraction/ → semantic_seg/
```

The segmentation task is **pure segmentation**: find where each semantic block starts and ends. There is no classification into predefined categories, and no per-document-type config file — the prompt is generic and specializes itself at runtime (see *The two nested loops* below).

A third module, `scraper/`, collected DOU publications from in.gov.br and was removed in `3781290`. It produced the reference corpus (`Pub_N.txt`, one file per publication) that `avaliar.py` still expects as ground truth. **That corpus is not in the repo** (it was gitignored) and is not currently on disk — see *Known Limitations*.

## Setup

```bash
pip install -r requirements.txt
# create .env with OPENAI_API_KEY=sk-...   (there is no .env.example)
```

`OPENAI_API_KEY` is required by `semantic_seg/` only. `text_extraction/` makes no API calls.

## Running Each Module

**Module 1a — download DOU edition PDFs** (edit the `EDITIONS` list at the top of the file):
```bash
cd text_extraction/
python download_pdfs.py
```
Fetches each page of an edition individually from `pesquisa.in.gov.br` and merges them into one PDF under `text_extraction/data/pdf/`.

**Module 1b — PDF → Markdown:**
```bash
cd text_extraction/
python pdf_extract.py -i arquivo.pdf -o saida/
python pdf_extract.py -i arquivo.pdf -o saida/ --workers 8   # parallel
python pdf_extract.py -i arquivo.pdf -o saida/ --no-resume   # ignore resume
python pdf_extract.py -i arquivo.pdf -o saida/ --no-final    # skip documento_final.md
python pdf_extract.py -i arquivo.pdf -o saida/ --chunk-size 4 # pages per worker chunk
```
`--workers` defaults to half the CPU count; `--chunk-size` defaults to auto.
Output: `saida/page_NNNN.md` per page (0-indexed, 4 digits) and `saida/documento_final.md`. Resumes automatically (skips already-processed pages).

**Module 1c — RTF → Text** (edit `ano`/`rtf_path` variables at top of file):
```bash
cd text_extraction/
python rtf_txt.py
```

**Module 2 — Semantic Segmentation:**
```bash
cd semantic_seg/
python main.py \
    --diretorio ../text_extraction/ppb_rules_out/paginas \
    --saida resultados/ppb_rules.json \
    --janela-paginas 10
```

| Flag | Meaning | Default |
|---|---|---|
| `--diretorio` | folder with the paginated `.md` files | required |
| `--extensao` | page file extension | `.md` |
| `--saida` | JSON file for the block list | none |
| `--model` | OpenAI model | `gpt-5.6-terra` |
| `--janela-paginas` | pages per context window | `10` |
| `--paginas-amostra` | pages per region (start/middle/end) sent to the identifier | `2` |
| `--sem-identificador` | skip pattern identification; the auditor deduces it from the blocks again | off |
| `--max-ciclos` | cap on correction cycles; `0` runs until the auditor approves | `0` |
| `--sem-correcao` | single pass, no corrector | off |
| `--so-resultado` | suppress prompt output | off |

Writes `{saida}.json` (block list only — the format `avaliar.py` consumes), plus siblings: `{saida}_padrao.json` (the identified pattern), `{saida}_cicloN.json` (each cycle's full extraction), `{saida}_correcao.json` (the correction trail). Existing files are never overwritten — `_v2`, `_v3` are appended instead.

**Evaluate segmentation results** (needs reference annotations — see *Known Limitations*):
```bash
cd semantic_seg/
python avaliar.py --resultado resultados/X.json --anotacoes <dir> --threshold 0.5 \
                  --relatorio resultados/X_relatorio.json

python avaliar.py --formato lei --resultado ... --anotacoes ...   # statute dataset
```

## The two nested loops

This is the core of `semantic_seg/` and the thing to understand before changing anything there.

**Outer loop — iterative correction** (`corretor.py:segmentar_com_correcao`): segment the whole document, have an LLM *auditor* judge the result, feed its directives back into the segmentation prompt, repeat. Stops when the auditor approves, when it produces no new directives, when the directives repeat (the next cycle would be identical), or at `--max-ciclos`.

**Inner loop — sliding window** (`utils_llm.py:processar_documento_completo`): the whole document is one string with `<!-- PÁGINA N -->` markers; each LLM call is asked for **only the first complete block** in the current window; a char pointer advances past each block via its `offset_fim` anchor. If a block's `pagina_fim` lands on the window's last page it may be truncated, so the window doubles and the call is retried.

**Before both** (`identificador.py`): the document's structural pattern is inferred **once**, from a sample of source pages — never from blocks. Its output (hierarchy, cut level, confidence) is injected into both the segmenter and the auditor prompts. This exists because the auditor only ever sees a summary of block *borders*, so deducing the pattern there is circular: a run on `ppb_rules` was approved as consistent while silently dropping item `(5) Determinations Required`, because a list ending at `(4)` followed by the next letter is indistinguishable from a complete one without the source text.

Prompt precedence, as stated in the prompts themselves: `padrao` is the structural spec; `insights` are corrections from observed failures and win any conflict.

## Architecture

### text_extraction/
- `download_pdfs.py`: Downloads DOU Section 1 full editions page-by-page from `pesquisa.in.gov.br` (8 threads, 3 retries, validates the `%PDF` magic bytes) and merges them with PyMuPDF. Editions are a hardcoded `EDITIONS` list.
- `pdf_extract.py`: Reads the native text layer from PDFs directly — no OCR, no ML models, no API calls. Three extraction strategies selected at import time: (1) **pymupdf4llm** (preferred, auto column/table detection → Markdown), (2) **PyMuPDF blocks + column sort** (fallback, heuristic multi-column reordering), (3) **plain `get_text()`** (last resort). Parallel extraction via `ProcessPoolExecutor` (`--workers N`). Warns on pages returning fewer than `MIN_PAGE_CHARS` (100) — likely scanned. Usable as a library: `from text_extraction.pdf_extract import extract_pdf`.
- `rtf_txt.py`: Converts legacy RTF law files to plain text via `striprtf`.

### semantic_seg/
- `main.py`: CLI entry point; loads pages, runs the identifier once, wires the pattern into both pipeline paths, persists results.
- `identificador.py`: Infers the document's structural pattern from `n` contiguous pages each from the start, middle and end (`amostrar_paginas`). Returns `tem_padrao`, `modo` (`hierarquico` / `sequencia_plana` / `topico`), `hierarquia`, `nivel_de_corte`, `confianca` — plus sample provenance added in code. `formatar_padrao()` renders that dict to prompt prose **in code**, so what reaches the model stays deterministic. `tem_padrao: false` is a real escape hatch: the auditor's schema has no equivalent and confabulates when its input is underdetermined.
- `utils_llm.py`: The sliding-window pipeline plus `completar_json()`, the single shared LLM entry point (JSON response format; `temperature=0` except on `gpt-5*`). `construir_prompt()` is generic, with two optional injected sections (`padrao`, `insights`).
- `corretor.py`: The auditor. `resumir_blocos()` sends only each block's page range, size, title and **borders** (250 leading / 120 trailing chars) — never the full text, which would cost as much as resending the document each cycle. The prompt has two branches: with an external `padrao` it checks conformance and drops `padrao_identificado` from its response schema; without one it deduces the pattern from the blocks (the pre-`identificador` behaviour, kept for `--sem-identificador`). It looks for five pathologies: uneven granularity, an engulfing block, overlap, gap, anchor failure.
- `anchor.py`: Tolerant anchor matching in **five layers** — exact; exact on the first 80 chars; normalized (HTML tags and page markers removed, markdown stripped, whitespace collapsed, accents decomposed, lowercased, with a position map back to the original); normalized truncated; and, for `offset_fim` only (`preferir_sufixo`), the last 40 chars. That last layer exists because the model cuts an anchor mid-word and reconstructs its *beginning* wrongly, while the end — the position that actually matters — is copied correctly. The full text is normalized once per run via an identity cache.
- `utils_files.py`: Loads paginated `.md` files sorted by filename; assembles the full text string; re-injects the page marker header when a window starts mid-page.
- `display.py`: Terminal rendering only — no pipeline logic.
- `avaliar.py`: Greedy matching (highest `word_f1` first) of predicted blocks against reference files. Reports Precision/Recall/F1 for detection plus average `word_f1`/`char_f1` for text quality. Handles DOU format (`Pub_N.txt`, optional `classes.json`) and statute format (`{seq}-{class}-{pag}-{pag}.txt`).

## Known Limitations

- **No reference data in the repo.** `avaliar.py` needs annotations that are not present for either format — no `Pub_*.txt`, no `classes.json`, no statute dataset. Until a corpus is restored, the correction loop's verdict and the identifier's pattern can only be inspected by hand, not scored. Running the loop until `consistente=true` is a **self-consistency** check, not a correctness one: a uniformly wrong segmentation is a fixed point.
- **Classification metrics in `avaliar.py` are orphaned.** It reads `bloco["classificacao"]` in several places, but no code writes that field any more — the prompt is segmentation-only. With `--formato lei` the classification block still runs and prints `Accuracy: 0/N`.
- **The identifier is a single point of failure.** Its pattern is injected as the structural criterion for both the segmenter and the auditor, so a wrong pattern is enforced faithfully and with more authority than before. `{saida}_padrao.json` exists to keep that auditable; `--sem-identificador` exists to A/B it.
- `pdf_extract.py` requires a native text layer; scanned/image-only PDFs need OCR.
- **`semantic_seg/lei.yaml` is vestigial** — its only consumer was `anotar_classes.py`, removed in `3781290`. No code reads it.
- **`requirements.txt` is stale**: it still lists the removed scraper's dependencies (`selenium`, `beautifulsoup4`, `lxml`, `requests`) and `marker-pdf`, from the PDF pipeline that `pdf_extract.py` replaced. ChromeDriver is no longer needed by anything.
