import json
import os
import unicodedata
from dotenv import load_dotenv
from openai import OpenAI
from utils_files import montar_texto_completo, _montar_janela

load_dotenv()


# ──────────────────────────────────────────────────────────────────────────────
# Prompt
# ──────────────────────────────────────────────────────────────────────────────

def construir_prompt(config: dict, texto_janela: str) -> str:
    """
    Monta o prompt completo que será enviado ao LLM.

    O prompt em si é **genérico** para qualquer tipo de bloco semântico.
    Especificidades do tipo de documento (o que define um bloco, regras
    de granularidade, exemplos de identificadores) ficam no arquivo de
    configuração (YAML), nos campos `definicao_bloco` e
    `regras_granularidade`, e são inseridas dinamicamente abaixo.
    """
    segmentos_formatados = "\n\n".join(
        f"{i+1}. **{s['nome']}**\n   {s['descricao']}"
        for i, s in enumerate(config["segmentos"])
    )

    definicao_bloco = (config.get("definicao_bloco") or
                       "Uma unidade textual coesa, com início e fim claramente delimitados, "
                       "que trata de um único assunto/ato dentro do tipo de documento analisado.").strip()

    regras_granularidade = (config.get("regras_granularidade") or "").strip()
    bloco_granularidade = (
        f"\n\n        ## Regras de granularidade (específicas deste tipo de documento)\n        {regras_granularidade}"
        if regras_granularidade else ""
    )

    return f"""Você é um especialista em análise de documentos oficiais brasileiros, com profundo conhecimento do {config["tipo_documento"]}.

        ## Descrição do tipo de documento
        {config["descricao_geral"]}

        ## Definição de bloco semântico (específica deste tipo de documento)
        {definicao_bloco}{bloco_granularidade}

        ## Categorias de classificação disponíveis
        As categorias abaixo representam os tipos de blocos semânticos que podem aparecer neste documento:

        {segmentos_formatados}

        ## Sua tarefa
        Analise o texto do documento fornecido abaixo e identifique **apenas o primeiro bloco semântico completo** presente no texto, conforme a definição e as regras de granularidade acima.

        O texto é composto por múltiplas páginas, cada uma precedida por um marcador `<!-- PÁGINA N -->`. Um bloco semântico pode se estender por mais de uma página.

        ## Texto do documento
        ```
        {texto_janela}
        ```

        ## Instruções de resposta
        Retorne **exclusivamente** um objeto JSON válido, sem texto adicional, com as seguintes chaves:

        - `"classificacao"` : string — nome exato de uma das categorias listadas acima
        - `"offset_inicio"` : string — trecho inicial (primeiras ~80 chars) do bloco, **COPIADO LITERALMENTE** do texto acima
        - `"offset_fim"`    : string — trecho final (últimas ~80 chars) do bloco, **COPIADO LITERALMENTE** do texto acima
        - `"pagina_inicio"` : inteiro — número da página onde o bloco começa (conforme os marcadores <!-- PÁGINA N -->)
        - `"pagina_fim"`    : inteiro — número da página onde o bloco termina (conforme os marcadores <!-- PÁGINA N -->)
        - `"titulo"`        : string — título ou identificador resumido do bloco
        - `"motivo"`        : string — justificativa curta da classificação escolhida

        ## Regras importantes (genéricas)
        - **Literalidade dos offsets**: `offset_inicio` e `offset_fim` devem ser trechos **literalmente presentes** no texto acima, **copiados sem qualquer modificação** — incluindo formatação markdown (`**`, `_`, `#`, etc.), pontuação, quebras de linha e maiúsculas/minúsculas. **NUNCA parafraseie, descreva, abrevie ou explique** o bloco nos offsets; eles servem apenas para localizar o trecho no texto fonte.
        - **Unicidade dos offsets**: cada offset deve ser suficientemente longo e distintivo para localização inequívoca no texto. Em caso de itens parecidos, escolha trechos mais longos ou mais únicos.
        - **Bloco completo**: não corte no meio de uma frase, cláusula ou identificador.
        - **Bloco mínimo, porém autossuficiente**: em caso de dúvida entre um bloco grande agrupando elementos correlatos vs. um bloco menor contendo apenas o primeiro elemento, prefira o menor — **desde que** o trecho menor seja autossuficiente (não dependa de cabeçalho, preâmbulo ou contexto que ficou fora dele para fazer sentido). Se o trecho menor perderia contexto essencial ao ser extraído isoladamente, inclua o contexto necessário no bloco.
        - Se o texto não contiver nenhum bloco semântico identificável, retorne `"classificacao": null` e todos os valores como `null` ou `0`.
        """


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _chamar_llm(config: dict, janela_texto: str, model: str, verboso: bool) -> dict:
    """Envia uma janela de texto ao LLM e retorna o dict JSON parseado."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    prompt = construir_prompt(config, janela_texto)

    if verboso:
        # print("\n── Prompt gerado ──────────────────────────────────────")
        # resumo = prompt[:3000] + "\n[...]\n" if len(prompt) > 3000 else prompt
        # print(resumo)
        print("── Chamando o LLM... ──────────────────────────────────\n")

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um assistente especializado em análise de documentos oficiais brasileiros. "
                    "Responda sempre com um único objeto JSON válido, sem texto adicional."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()

    # Remove blocos de código markdown caso o modelo os inclua
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def _construir_mapa_paginas(texto_completo: str, paginas: list[dict]) -> list[tuple[int, int]]:
    """
    Mapeia cada página ao seu índice de início no texto_completo.

    Retorna
    -------
    Lista de (pagina_num_1indexed, char_pos_inicio) ordenada por posição.
    """
    mapa = []
    for p in paginas:
        marcador = f"<!-- PÁGINA {p['pagina']} -->"
        idx = texto_completo.find(marcador)
        if idx != -1:
            mapa.append((p["pagina"], idx))
    # Garante ordenação por posição no texto
    mapa.sort(key=lambda x: x[1])
    return mapa


def _pos_fim_janela(mapa: list[tuple[int, int]], idx_pagina_fim: int, len_total: int) -> int:
    """Retorna a posição de caractere que representa o fim da janela."""
    if idx_pagina_fim < len(mapa):
        return mapa[idx_pagina_fim][1]
    return len_total


# ──────────────────────────────────────────────────────────────────────────────
# Matching tolerante de âncoras
# ──────────────────────────────────────────────────────────────────────────────

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


def _avançar_por_offset(
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


def _idx_pagina_de_pos(mapa: list[tuple[int, int]], pos: int) -> int:
    """
    Retorna o índice (0-based) na lista mapa correspondente à página
    que contém a posição de caractere `pos`.
    """
    resultado = 0
    for i, (_, ppos) in enumerate(mapa):
        if ppos <= pos:
            resultado = i
        else:
            break
    return resultado


def _num_pagina_de_idx(mapa: list[tuple[int, int]], idx: int) -> int:
    """Retorna o número de página (1-indexed) dado o índice no mapa."""
    if idx < len(mapa):
        return mapa[idx][0]
    return mapa[-1][0] if mapa else 0


def _extrair_trecho(
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


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline principal — janela deslizante
# ──────────────────────────────────────────────────────────────────────────────

def processar_documento_completo(
    config: dict,
    paginas: list[dict],
    model: str = "gpt-4o",
    verboso: bool = True,
    janela_paginas: int = 20,
) -> list[dict]:
    """
    Percorre o documento inteiro via janela deslizante, identificando
    todos os blocos semânticos de forma iterativa.

    Estratégia
    ----------
    1. Monta o texto completo uma única vez, com marcadores <!-- PÁGINA N -->.
       Os números de página nos marcadores são sempre absolutos (originais),
       então os valores retornados pelo LLM são diretamente comparáveis ao
       documento fonte.

    2. Mantém `pos_atual` como ponteiro de caractere no texto completo.
       Após cada bloco identificado, localiza `offset_fim` no texto e avança
       `pos_atual` para imediatamente após esse trecho — preservando qualquer
       conteúdo que exista entre o fim do bloco e o fim da página.

    3. Detecção de truncamento: se `pagina_fim` do resultado coincidir com a
       última página da janela atual, o bloco pode estar incompleto. Nesse
       caso, a janela é estendida automaticamente até o dobro do tamanho
       original antes de uma nova tentativa.

    Parâmetros
    ----------
    config         : dict de configuração (tipo_documento, descricao_geral, segmentos)
    paginas        : lista de dicts retornada por carregar_paginas()
    model          : modelo OpenAI a utilizar
    verboso        : se True, imprime prompts e progresso detalhado
    janela_paginas : número de páginas por janela de contexto

    Retorna
    -------
    Lista de dicts, um por bloco identificado.
    """
    texto_completo  = montar_texto_completo(paginas)
    mapa            = _construir_mapa_paginas(texto_completo, paginas)
    total_paginas   = len(paginas)
    len_texto       = len(texto_completo)

    blocos        = []
    pos_atual     = 0       # ponteiro de char no texto_completo
    idx_pag_atual = 0       # índice 0-based no mapa de páginas
    iteracao      = 0
    MAX_ITER      = total_paginas * 15  # teto de segurança anti-loop infinito

    SEP = "═" * 62
    print(f"\n{SEP}")
    print(f"  Pipeline — janela deslizante")
    print(f"  {total_paginas} página(s) | janela = {janela_paginas} págs. | modelo = {model}")
    print(f"{SEP}\n")

    while idx_pag_atual < total_paginas and iteracao < MAX_ITER:
        iteracao += 1

        # ── Define os limites da janela atual ─────────────────────────────
        idx_pag_fim  = min(idx_pag_atual + janela_paginas, total_paginas)
        pos_fim_jan  = _pos_fim_janela(mapa, idx_pag_fim, len_texto)
        # janela_texto = texto_completo[pos_atual:pos_fim_jan]
        janela_texto = _montar_janela(texto_completo, mapa, idx_pag_atual, pos_atual, pos_fim_jan)
        
        if not janela_texto.strip():
            print("  ⚠  Janela vazia — fim do documento alcançado.")
            break

        pag_ini_str = _num_pagina_de_idx(mapa, idx_pag_atual)
        pag_fim_str = _num_pagina_de_idx(mapa, idx_pag_fim - 1)
        print(
            f"── Iteração {iteracao:>3} │ págs. {pag_ini_str}–{pag_fim_str} "
            f"│ {len(janela_texto):>8,} chars ──"
        )

        # ── Chama o LLM ───────────────────────────────────────────────────
        resultado = _chamar_llm(config, janela_texto, model, verboso)
        print(resultado)

        # ── Bloco não encontrado — avança 1 página e continua ────────────
        if not resultado.get("classificacao"):
            print(f"  ⚠  Nenhum bloco identificado. Avançando 1 página...")
            idx_pag_atual = min(idx_pag_atual + 1, total_paginas)
            pos_atual = mapa[idx_pag_atual][1] if idx_pag_atual < total_paginas else len_texto
            continue

        # ── Verificação de truncamento ─────────────────────────────────────
        # Se pagina_fim bate com a última página da janela, o bloco pode
        # ter sido cortado. Expande a janela e tenta de novo.
        pag_fim_resultado  = resultado.get("pagina_fim", 0)
        pag_fim_janela_num = _num_pagina_de_idx(mapa, idx_pag_fim - 1)

        if pag_fim_resultado >= pag_fim_janela_num and idx_pag_fim < total_paginas:
            janela_expandida = min(janela_paginas * 2, total_paginas - idx_pag_atual)
            print(
                f"  ⚠  Bloco pode estar truncado (pagina_fim={pag_fim_resultado} "
                f"= última pág. da janela). Expandindo para {janela_expandida} págs..."
            )
            idx_pag_fim_exp  = min(idx_pag_atual + janela_expandida, total_paginas)
            pos_fim_jan_exp  = _pos_fim_janela(mapa, idx_pag_fim_exp, len_texto)
            janela_texto_exp = texto_completo[pos_atual:pos_fim_jan_exp]

            resultado = _chamar_llm(config, janela_texto_exp, model, verboso)

            if not resultado.get("classificacao"):
                print("  ⚠  Ainda sem bloco após expansão. Avançando meia janela.")
                idx_pag_atual = min(idx_pag_atual + max(1, janela_paginas // 2), total_paginas)
                pos_atual     = mapa[idx_pag_atual][1] if idx_pag_atual < total_paginas else len_texto
                continue

        # ── Avança posição via offset_fim ─────────────────────────────────
        pos_antes_do_bloco = pos_atual
        offset_fim = resultado.get("offset_fim", "")
        nova_pos   = _avançar_por_offset(texto_completo, offset_fim, pos_atual)

        if nova_pos == -1:
            # Fallback 1: avança para logo após offset_inicio — progresso
            # mínimo que mantém o pipeline dentro da mesma página, evitando
            # pular blocos curtos que seguem o bloco identificado.
            offset_inicio = resultado.get("offset_inicio", "")
            pos_apos_inicio = _avançar_por_offset(
                texto_completo, offset_inicio, pos_antes_do_bloco
            )
            if pos_apos_inicio != -1:
                print(
                    f"  ⚠  offset_fim não localizado. "
                    f"Avançando para após offset_inicio."
                )
                pos_atual     = pos_apos_inicio
                idx_pag_atual = _idx_pagina_de_pos(mapa, pos_atual)
            else:
                # Fallback 2: ambas as âncoras falharam — avança para a
                # página seguinte ao pagina_fim como último recurso.
                print(
                    f"  ⚠  offset_fim e offset_inicio não localizados. "
                    f"Avançando até após a pág. {pag_fim_resultado}."
                )
                idx_apos_bloco = None
                for i, (pnum, _) in enumerate(mapa):
                    if pnum == pag_fim_resultado:
                        idx_apos_bloco = i + 1
                        break

                if idx_apos_bloco is not None and idx_apos_bloco < total_paginas:
                    idx_pag_atual = idx_apos_bloco
                    pos_atual     = mapa[idx_pag_atual][1]
                else:
                    idx_pag_atual = total_paginas
                    pos_atual     = len_texto
        else:
            pos_atual     = nova_pos
            idx_pag_atual = _idx_pagina_de_pos(mapa, pos_atual)

        # ── Extrai o trecho completo do documento original ────────────────
        # pos_busca_inicio aponta para antes do início da janela atual,
        # evitando que o match recaia sobre uma ocorrência anterior idêntica.
        trecho = _extrair_trecho(
            texto_completo,
            resultado.get("offset_inicio", ""),
            resultado.get("offset_fim", ""),
            pos_busca_inicio=pos_antes_do_bloco,
        )
        resultado["texto"] = trecho  # None se as âncoras não forem encontradas

        # ── Registra o bloco ───────────────────────────────────────────────
        blocos.append(resultado)

        titulo  = resultado.get("titulo", "N/A")
        classif = resultado.get("classificacao", "?")
        p_ini   = resultado.get("pagina_inicio", "?")
        p_fim   = resultado.get("pagina_fim", "?")
        pct     = pos_atual / len_texto * 100

        print(
            f"  ✓ Bloco {len(blocos):>3}: [{classif}] {titulo}\n"
            f"           págs. {p_ini}–{p_fim} │ "
            f"nova pos = char {pos_atual:,} ({pct:.1f}% do doc)"
        )

    print(f"\n{SEP}")
    print(f"  Concluído: {len(blocos)} bloco(s) em {iteracao} iteração(ões).")
    print(f"{SEP}\n")

    return blocos


# ──────────────────────────────────────────────────────────────────────────────
# Compatibilidade retroativa — identifica apenas o primeiro bloco
# ──────────────────────────────────────────────────────────────────────────────

def identificar_primeiro_bloco(
    config: dict,
    paginas: list[dict],
    model: str = "gpt-4o",
    verboso: bool = True,
) -> dict:
    """
    Identifica apenas o primeiro bloco semântico do documento.
    Mantido para compatibilidade retroativa.
    """
    texto_completo = montar_texto_completo(paginas)
    return _chamar_llm(config, texto_completo, model, verboso)


# ──────────────────────────────────────────────────────────────────────────────
# Exibição
# ──────────────────────────────────────────────────────────────────────────────

def exibir_resultado(resultado: dict) -> None:
    """Exibe um único bloco no terminal."""
    print("── Resultado ──────────────────────────────────────────")
    if not resultado.get("classificacao"):
        print("  Nenhum bloco semântico identificado no texto.")
        return

    pagina_inicio = resultado.get("pagina_inicio", "?")
    pagina_fim    = resultado.get("pagina_fim", "?")
    paginas_str   = (
        f"pág. {pagina_inicio}"
        if pagina_inicio == pagina_fim
        else f"págs. {pagina_inicio}–{pagina_fim}"
    )

    print(f"  Classificação  : {resultado['classificacao']}")
    print(f"  Título         : {resultado.get('titulo', 'N/A')}")
    print(f"  Páginas        : {paginas_str}")
    print(f"  Offset início  : {resultado['offset_inicio']}")
    print(f"  Offset fim     : {resultado['offset_fim']}")
    print(f"  Motivo         : {resultado.get('motivo', '')}")
    texto = resultado.get("texto")
    if texto:
        preview = texto[:300].replace("\n", "↵ ")
        reticencias = "..." if len(texto) > 300 else ""
        print(f"  Texto ({len(texto):,} chars): {preview}{reticencias}")
    else:
        print(f"  Texto          : ⚠ não extraído (âncoras não localizadas)")
    print(f"  {'─' * 50}")


def exibir_resumo_blocos(blocos: list[dict]) -> None:
    """Exibe um resumo tabular de todos os blocos identificados."""
    SEP = "─" * 70
    print(f"\n{SEP}")
    print(f"  {'#':>3}  {'Págs.':^12}  {'Classificação':<25}  Título")
    print(SEP)
    for i, b in enumerate(blocos, 1):
        p_ini   = b.get("pagina_inicio", "?")
        p_fim   = b.get("pagina_fim", "?")
        paginas = f"{p_ini}–{p_fim}" if p_ini != p_fim else str(p_ini)
        classif = (b.get("classificacao") or "")[:25]
        titulo  = (b.get("titulo") or "N/A")[:35]
        print(f"  {i:>3}  {paginas:^12}  {classif:<25}  {titulo}")
    print(SEP)
    print(f"  Total: {len(blocos)} bloco(s)\n")