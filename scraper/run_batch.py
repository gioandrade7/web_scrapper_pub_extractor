"""
Batch runner para pub_scrapper.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Executa o scraper sequencialmente para cada DOU faltante,
ou seja, os que existem em semantic_seg/out/dou/blocos mas
ainda não têm diretório correspondente em pubs_extracted/.

Como usar:
    cd docAI/scraper
    python run_batch.py
"""

import asyncio
import logging
import time
from pathlib import Path

# Importa as funções do scraper existente
from pub_scrapper import (
    collect_links_and_cookies,
    process_async,
    process_fallback,
    get_date_sec,
    _counter,
    _counter_lock,
)

log = logging.getLogger(__name__)

# 11 DOUs faltantes (identificados a partir dos JSONs em semantic_seg/out/dou/blocos)
# Cada item: (url, nome_diretorio_customizado_ou_None)
URLS: list[tuple[str, str | None]] = [
    ("https://in.gov.br/leiturajornal?data=16-06-2025&secao=do2", None),                    # dou_sec2_16-06
    ("https://in.gov.br/leiturajornal?data=17-06-2025&secao=do2", None),                    # dou_sec2_17-06
    ("https://in.gov.br/leiturajornal?data=18-03-2025&secao=do2", None),                    # dou_sec2_18-03
    ("https://in.gov.br/leiturajornal?data=19-10-2022&secao=do2", None),                    # dou_sec2_19-10
    ("https://in.gov.br/leiturajornal?data=19-12-2022&secao=do2", None),                    # dou_sec2_19-12
    ("https://in.gov.br/leiturajornal?data=21-10-2024&secao=do2", None),                    # dou_sec2_21-10
    ("https://in.gov.br/leiturajornal?data=22-07-2024&secao=do2", None),                    # dou_sec2_22-07
    ("https://in.gov.br/leiturajornal?data=22-12-2022&secao=do2", "dou_sec2_22-12_2022"),   # dou_sec2_22-12_2022
    ("https://in.gov.br/leiturajornal?data=22-12-2023&secao=do2", "dou_sec2_22-12_2023"),   # dou_sec2_22-12_2023
    ("https://in.gov.br/leiturajornal?data=23-07-2024&secao=do2", None),                    # dou_sec2_23-07
    ("https://in.gov.br/leiturajornal?data=23-12-2022&secao=do2", None),                    # dou_sec2_23-12
]

OUTPUT_BASE = Path(__file__).parent / "pubs_extracted"


def run_for_url(url: str, custom_name: str | None = None) -> None:
    data, sec = get_date_sec(url)
    dir_name = custom_name if custom_name else f"dou_sec{sec}_{data}"
    output_dir = OUTPUT_BASE / dir_name

    if output_dir.exists() and any(output_dir.iterdir()):
        log.info(f"Diretório já preenchido, pulando: {output_dir.name}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    log.info(f"{'='*60}")
    log.info(f"Iniciando: {output_dir.name}")
    log.info(f"URL: {url}")

    # Resetar contadores globais do módulo
    with _counter_lock:
        _counter["done"] = 0
        _counter["fail"] = 0
        _counter["total"] = 0

    links, cookies = collect_links_and_cookies(url)
    if not links:
        log.error(f"Nenhum link encontrado para {output_dir.name}. Pulando.")
        return

    with _counter_lock:
        _counter["total"] = len(links)

    log.info(f"Extraindo {len(links)} publicação(ões) via HTTP assíncrono…")
    t0 = time.perf_counter()

    failed = asyncio.run(process_async(links, cookies, output_dir))
    process_fallback(failed, output_dir)

    elapsed = time.perf_counter() - t0
    log.info(
        f"Concluído {output_dir.name} em {elapsed:.1f}s | "
        f"{_counter['done']} salvas, {_counter['fail']} falha(s)."
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info(f"Batch iniciado: {len(URLS)} DOU(s) a processar.")
    total_start = time.perf_counter()

    for i, (url, custom_name) in enumerate(URLS, 1):
        log.info(f"\n[{i}/{len(URLS)}] Processando: {url}")
        try:
            run_for_url(url, custom_name)
        except Exception as e:
            log.error(f"Erro inesperado para {url}: {e}")

    elapsed = time.perf_counter() - total_start
    log.info(f"\nBatch finalizado em {elapsed / 60:.1f} min.")


if __name__ == "__main__":
    main()
