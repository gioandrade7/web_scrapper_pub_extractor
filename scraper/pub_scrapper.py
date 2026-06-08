"""
Scraper do Diário Oficial da União (DOU) — Versão Otimizada
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Melhorias em relação à versão anterior:

  1. Selenium usado SOMENTE para coleta de links + captura de cookies.
     Após essa etapa, o driver é encerrado.
  2. httpx assíncrono com os cookies capturados substitui os N drivers
     Selenium para extração de conteúdo — elimina o overhead pesado de
     múltiplos navegadores Chrome.
  3. Semáforo controla concorrência (padrão: 20 req simultâneas) sem
     bloquear o event loop.
  4. Backoff exponencial assíncrono (sem time.sleep bloqueante).
  5. Fallback automático para Selenium nos casos raros de 403 persistente.
  6. Polling de estabilização da árvore usa condição dinâmica (sem sleep
     fixo de 5 s).
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import httpx
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Configurações ────────────────────────────────────────────────────────────

MAX_CONCURRENT   = 20   # Requisições HTTP simultâneas
MAX_RETRIES      = 3    # Tentativas por link
HTTP_TIMEOUT     = 15   # Timeout de cada requisição (segundos)
WAIT_AFTER_FAIL  = 2    # Espera base entre retries (dobra a cada falha)

# Fallback Selenium (para URLs que o httpx não consiga)
NUM_DRIVERS_FALLBACK = 3
PAGE_TIMEOUT         = 20

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_counter_lock = Lock()
_counter = {"done": 0, "fail": 0, "total": 0}

# Headers realistas para evitar bloqueios básicos
_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://in.gov.br/",
}

# ── Utilitários ──────────────────────────────────────────────────────────────

def get_date_sec(link: str) -> tuple[str, str]:
    """Extrai data e seção da URL do DOU."""
    parts   = link.split("data=")[1].split("&secao=")
    date    = parts[0][:5]   # ex: "06-01"
    section = parts[1][-1]   # ex: "1"
    return date, section


def setup_driver() -> webdriver.Chrome:
    """Configura o Chrome WebDriver no modo headless."""
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)

# ── Coleta de links + cookies (único driver Selenium) ────────────────────────

def collect_links_and_cookies(url: str) -> tuple[list[str], dict]:
    """
    Abre o DOU com Selenium, coleta links da árvore de publicações
    e captura os cookies de sessão para reutilizar nas requisições HTTP.
    """
    driver = setup_driver()
    log.info("Driver inicializado para coleta de links e cookies…")

    try:
        driver.get(url)

        # Clica no botão de árvore
        tree_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "viewMenuOptionTree"))
        )
        driver.execute_script("arguments[0].click();", tree_button)

        # Aguarda o primeiro item aparecer
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li.file a"))
        )

        # Aguarda estabilização da lista (contagem parou de crescer)
        prev_count = 0
        for _ in range(20):
            files = driver.find_elements(By.CSS_SELECTOR, "li.file a")
            curr_count = len(files)
            if curr_count > 0 and curr_count == prev_count:
                break
            prev_count = curr_count
            time.sleep(0.3)   # intervalo menor que o original (0.5s)

        links = [f.get_attribute("href") for f in files if f.get_attribute("href")]

        # Captura cookies para autenticar as requisições HTTP
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}

        log.info(f"{len(links)} link(s) coletado(s), {len(cookies)} cookie(s) capturado(s).")
        return links, cookies

    except Exception as e:
        log.error(f"Erro ao coletar links: {e}")
        return [], {}

    finally:
        driver.quit()

# ── Extração de texto HTML ────────────────────────────────────────────────────

def _parse_texto_dou(html: str) -> str | None:
    soup  = BeautifulSoup(html, "lxml")
    texto = soup.find(class_="texto-dou")
    if not texto:
        return None
    return " ".join(p.get_text(strip=True) for p in texto.find_all("p"))

# ── Extração assíncrona com httpx ─────────────────────────────────────────────

async def _fetch_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    index: int,
    url: str,
) -> tuple[int, str | None]:
    """Busca e parseia uma publicação com retries e backoff exponencial."""
    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.get(url, timeout=HTTP_TIMEOUT)

                if resp.status_code == 200:
                    return index, _parse_texto_dou(resp.text)

                if resp.status_code == 429:
                    wait = WAIT_AFTER_FAIL * (2 ** attempt)
                    log.warning(f"Rate-limit (429) em Pub_{index}. Aguardando {wait}s…")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code in (403, 401):
                    log.warning(
                        f"Acesso negado ({resp.status_code}) para Pub_{index} "
                        f"(tentativa {attempt}/{MAX_RETRIES})."
                    )
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(WAIT_AFTER_FAIL * attempt)
                    else:
                        return index, None

                else:
                    log.warning(f"HTTP {resp.status_code} para Pub_{index}.")
                    return index, None

            except Exception as e:
                wait = WAIT_AFTER_FAIL * attempt
                log.warning(
                    f"Erro na tentativa {attempt}/{MAX_RETRIES} para Pub_{index}: "
                    f"{e}. Aguardando {wait}s…"
                )
                await asyncio.sleep(wait)

    return index, None


async def process_async(
    links: list[str],
    cookies: dict,
    output_dir: Path,
) -> list[tuple[int, str]]:
    """
    Extrai todas as publicações de forma assíncrona com httpx.
    Retorna lista de (index, url) que falharam para fallback com Selenium.
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    failed: list[tuple[int, str]] = []

    async with httpx.AsyncClient(
        headers=_HTTP_HEADERS,
        cookies=cookies,
        follow_redirects=True,
        http2=True,
    ) as client:
        tasks = [
            _fetch_one(client, semaphore, i, url)
            for i, url in enumerate(links)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            log.error(f"Exceção inesperada: {result}")
            continue

        index, content = result

        with _counter_lock:
            if content:
                _counter["done"] += 1
            else:
                _counter["fail"] += 1
            done  = _counter["done"]
            fail  = _counter["fail"]
            total = _counter["total"]

        if content:
            file_path = output_dir / f"Pub_{index}.txt"
            file_path.write_text(content, encoding="utf-8")
            log.info(f"[{done + fail}/{total}] Pub_{index} salva.")
        else:
            failed.append((index, links[index]))
            log.warning(f"[{done + fail}/{total}] Pub_{index} falhou via HTTP.")

    return failed

# ── Fallback Selenium (somente para URLs que o httpx não resolveu) ────────────

def _selenium_worker(job_queue, output_dir: Path) -> None:
    driver = setup_driver()
    try:
        while True:
            try:
                index, url = job_queue.get_nowait()
            except Exception:
                break

            try:
                driver.get(url)
                WebDriverWait(driver, PAGE_TIMEOUT).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "texto-dou"))
                )
                content = _parse_texto_dou(driver.page_source)
                if content:
                    file_path = output_dir / f"Pub_{index}.txt"
                    file_path.write_text(content, encoding="utf-8")
                    log.info(f"Fallback OK: Pub_{index}")
                    with _counter_lock:
                        _counter["done"] += 1
                        _counter["fail"] -= 1
            except Exception as e:
                log.error(f"Fallback falhou para Pub_{index}: {e}")
            finally:
                job_queue.task_done()
    finally:
        driver.quit()


def process_fallback(failed: list[tuple[int, str]], output_dir: Path) -> None:
    """Processa com Selenium as URLs que o httpx não conseguiu extrair."""
    if not failed:
        return

    import queue
    log.info(f"Fallback Selenium para {len(failed)} URL(s)…")
    job_queue: queue.Queue = queue.Queue()
    for item in failed:
        job_queue.put(item)

    n = min(NUM_DRIVERS_FALLBACK, len(failed))
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [executor.submit(_selenium_worker, job_queue, output_dir) for _ in range(n)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as e:
                log.error(f"Erro no worker Selenium: {e}")

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://in.gov.br/leiturajornal?data=18-03-2026&secao=do1")
    args = parser.parse_args()
    url = args.url

    data, sec  = get_date_sec(url)
    output_dir = Path(f"pubs_extracted/dou_sec{sec}_{data}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Coleta links + cookies (único driver Selenium)
    links, cookies = collect_links_and_cookies(url)
    if not links:
        log.error("Nenhum link encontrado. Encerrando.")
        return

    _counter["total"] = len(links)
    log.info(f"Extraindo {len(links)} publicação(ões) via HTTP assíncrono…")

    t0 = time.perf_counter()

    # 2. Extração assíncrona rápida
    failed = asyncio.run(process_async(links, cookies, output_dir))

    # 3. Fallback Selenium para casos persistentes
    process_fallback(failed, output_dir)

    elapsed = time.perf_counter() - t0
    log.info(
        f"Concluído em {elapsed:.1f}s | "
        f"{_counter['done']} salvas, {_counter['fail']} falha(s). "
        f"Saída: {output_dir}"
    )


if __name__ == "__main__":
    main()
