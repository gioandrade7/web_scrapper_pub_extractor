"""
Extração de texto de publicações do DOU — Versão Otimizada
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Melhorias em relação à versão anterior:

  1. Substituição de Selenium por requests — sem overhead de navegador.
  2. Sessão HTTP reutilizável entre chamadas (connection pool).
  3. Fallback para Selenium (driver singleton) quando a requisição HTTP
     é bloqueada (403/401), sem criar um novo driver a cada chamada.
  4. Driver Selenium encerrado corretamente ao fim do uso.
"""

from __future__ import annotations

import requests
from bs4 import BeautifulSoup
from functools import lru_cache
from typing import Optional

# ── Sessão HTTP reutilizável ──────────────────────────────────────────────────

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

# Sessão compartilhada — mantém connection pool e cookies entre chamadas
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(_HTTP_HEADERS)
    return _session


# ── Parser HTML compartilhado ─────────────────────────────────────────────────

def _parse_texto_dou(html: str) -> Optional[str]:
    soup  = BeautifulSoup(html, "lxml")
    texto = soup.find(class_="texto-dou")
    if not texto:
        return None
    return " ".join(p.get_text(strip=True) for p in texto.find_all("p"))


# ── Extração via requests (principal) ────────────────────────────────────────

def _fetch_via_http(url: str, timeout: int = 15) -> Optional[str]:
    try:
        resp = _get_session().get(url, timeout=timeout)
        if resp.status_code == 200:
            return _parse_texto_dou(resp.text)
        # 403/401 → sinaliza para usar o fallback Selenium
        if resp.status_code in (401, 403):
            return None
    except requests.RequestException:
        pass
    return None


# ── Fallback: driver Selenium singleton ──────────────────────────────────────

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--blink-settings=imagesEnabled=false")
        options.add_argument("--disable-extensions")
        _driver = webdriver.Chrome(options=options)
    return _driver


def _fetch_via_selenium(url: str, timeout: int = 20) -> Optional[str]:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = _get_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CLASS_NAME, "texto-dou"))
        )
        return _parse_texto_dou(driver.page_source)
    except Exception:
        return None


def close_driver() -> None:
    """Encerra o driver Selenium se estiver ativo. Chamar ao final do script."""
    global _driver
    if _driver is not None:
        _driver.quit()
        _driver = None


# ── API pública ───────────────────────────────────────────────────────────────

def text_extraction(url: str) -> str:
    """
    Extrai o texto de uma publicação do DOU a partir da URL.

    Tenta primeiro via requests (rápido, sem overhead de browser).
    Se bloqueado (403/401), usa o driver Selenium singleton como fallback.

    Returns:
        Texto extraído ou string vazia se não encontrado.
    """
    result = _fetch_via_http(url)
    if result is not None:
        return result

    # Fallback: Selenium (reutiliza driver — não cria um novo por chamada)
    result = _fetch_via_selenium(url)
    return result or ""
