"""
anchor.py — Matching tolerante de âncoras.

O LLM devolve trechos "copiados literalmente" (offset_inicio / offset_fim) que,
na prática, sofrem pequenas variações: marcação markdown, acentos, espaços em
branco colapsados, maiúsculas/minúsculas. Este módulo reencontra esses trechos
no texto-fonte com uma cascata de 4 camadas de tolerância.

É a parte "assustadora, porém isolada" do pipeline: mexa aqui apenas quando
estiver depurando por que uma âncora não foi localizada.
"""

import unicodedata


_MARKDOWN_CHARS = frozenset("_*#`~>")


def _normalizar(texto: str) -> tuple[str, list[int]]:
    """
    Normaliza `texto` para matching tolerante.

    Aplica, na ordem:
    1. Remove marcadores markdown inline (`_ * # ` ~ >`).
    2. Colapsa qualquer sequência de whitespace em um único espaço.
    3. Decompõe acentos (NFD) e descarta caracteres combinantes.
    4. Converte para minúsculas.

    Retorna (normalizado, mapa) onde `mapa[i]` é a posição em `texto`
    original do char `normalizado[i]`. Permite recuperar offsets do
    texto original a partir de um match feito no espaço normalizado.
    """
    chars: list[str] = []
    mapa: list[int] = []
    prev_space = True  # evita espaço inicial

    for i, ch in enumerate(texto):
        if ch in _MARKDOWN_CHARS:
            continue
        if ch.isspace():
            if not prev_space:
                chars.append(" ")
                mapa.append(i)
                prev_space = True
            continue
        decomp = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in decomp if unicodedata.category(c) != "Mn")
        for c in base.lower():
            chars.append(c)
            mapa.append(i)
        prev_space = False

    return "".join(chars), mapa


_norm_cache_texto: str | None = None
_norm_cache_resultado: tuple[str, list[int]] | None = None


def _normalizar_texto_cached(texto: str) -> tuple[str, list[int]]:
    """Cache de identidade para a normalização do texto completo (reusado em toda iteração)."""
    global _norm_cache_texto, _norm_cache_resultado
    if _norm_cache_texto is not texto:
        _norm_cache_texto = texto
        _norm_cache_resultado = _normalizar(texto)
    return _norm_cache_resultado  # type: ignore[return-value]


def _localizar_ancora(
    texto: str,
    ancora: str,
    pos_busca: int = 0,
) -> tuple[int, int]:
    """
    Localiza `ancora` em `texto` a partir de `pos_busca` com matching em camadas.

    Estratégia
    ----------
    1. `find()` exato sobre a âncora completa.
    2. `find()` exato sobre os primeiros 80 chars (caso o LLM tenha truncado).
    3. `find()` em versão normalizada (markdown removido, whitespace colapsado,
       acentos removidos, lowercase) — mapeia a posição encontrada de volta
       para o texto original.
    4. Mesmo passo 3 mas com a âncora normalizada truncada a 80 chars.

    Retorna `(pos_inicio, pos_fim)` no texto original, com `pos_fim` exclusivo
    (posição imediatamente após o último char da âncora). `(-1, -1)` se nenhuma
    camada encontrar.
    """
    if not ancora:
        return -1, -1

    # Camada 1: exato
    idx = texto.find(ancora, pos_busca)
    if idx != -1:
        return idx, idx + len(ancora)

    # Camada 2: exato sobre primeiros 80 chars
    parcial = ancora[:80].strip()
    if parcial and parcial != ancora:
        idx = texto.find(parcial, pos_busca)
        if idx != -1:
            return idx, idx + len(parcial)

    # Camadas 3–4: matching normalizado
    norm_texto, mapa = _normalizar_texto_cached(texto)
    norm_ancora, _ = _normalizar(ancora)
    if not norm_ancora:
        return -1, -1

    # Traduz pos_busca para o espaço normalizado (primeiro índice cuja
    # posição original >= pos_busca).
    norm_pos_busca = len(mapa)
    for i, p in enumerate(mapa):
        if p >= pos_busca:
            norm_pos_busca = i
            break

    def _match_em_normalizado(alvo: str) -> tuple[int, int]:
        idx_n = norm_texto.find(alvo, norm_pos_busca)
        if idx_n == -1:
            return -1, -1
        pos_ini = mapa[idx_n]
        pos_fim = mapa[idx_n + len(alvo) - 1] + 1
        return pos_ini, pos_fim

    pos_ini, pos_fim = _match_em_normalizado(norm_ancora)
    if pos_ini != -1:
        return pos_ini, pos_fim

    norm_parcial = norm_ancora[:80].strip()
    if norm_parcial and norm_parcial != norm_ancora:
        return _match_em_normalizado(norm_parcial)

    return -1, -1


def avancar_por_offset(
    texto_completo: str,
    offset_fim: str,
    pos_atual: int,
) -> int:
    """
    Localiza offset_fim no texto a partir de pos_atual e retorna a posição
    imediatamente após o fim do trecho. -1 se não encontrar.

    Delega para `_localizar_ancora`, que aplica matching tolerante
    (markdown, whitespace, acentos, case).
    """
    _, pos_fim = _localizar_ancora(texto_completo, offset_fim, pos_atual)
    return pos_fim


def extrair_trecho(
    texto_completo: str,
    offset_inicio: str,
    offset_fim: str,
    pos_busca_inicio: int = 0,
) -> str | None:
    """
    Extrai o trecho completo do bloco usando offset_inicio e offset_fim
    como âncoras. Usa matching tolerante via `_localizar_ancora`.

    Retorna o slice `texto_completo[pos_ini:pos_fim]` (inclui o próprio
    offset_fim), ou None se qualquer âncora não for encontrada.
    """
    if not offset_inicio or not offset_fim:
        return None

    pos_ini, _ = _localizar_ancora(texto_completo, offset_inicio, pos_busca_inicio)
    if pos_ini == -1:
        return None

    _, pos_fim = _localizar_ancora(texto_completo, offset_fim, pos_ini)
    if pos_fim == -1:
        return None

    return texto_completo[pos_ini:pos_fim]
