import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from utils_files import montar_texto_completo, _montar_janela
from anchor import avancar_por_offset, extrair_trecho

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
# Chamada ao LLM
# ──────────────────────────────────────────────────────────────────────────────

def _chamar_llm(config: dict, janela_texto: str, model: str, verboso: bool) -> dict:
    """Envia uma janela de texto ao LLM e retorna o dict JSON parseado."""
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    prompt = construir_prompt(config, janela_texto)

    if verboso:
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


# ──────────────────────────────────────────────────────────────────────────────
# Mapa de páginas
#
# `carregar_paginas` numera as páginas sequencialmente (1..N), então a página
# de número K está SEMPRE no índice K-1. Basta, portanto, guardar a posição de
# caractere do marcador de cada página numa lista simples: `posicoes[idx]` é o
# início da página `idx + 1`. (Antes isto era uma lista de tuplas
# (num_pagina, posicao), o que forçava conversões constantes entre índice
# 0-based e número de página 1-based.)
# ──────────────────────────────────────────────────────────────────────────────

def _mapear_paginas(texto_completo: str, total_paginas: int) -> list[int]:
    """Posição de caractere do marcador `<!-- PÁGINA K -->` de cada página."""
    return [
        texto_completo.find(f"<!-- PÁGINA {pagina} -->")
        for pagina in range(1, total_paginas + 1)
    ]


def _pos_de_idx(posicoes: list[int], idx: int, len_texto: int) -> int:
    """Posição de início da página no índice `idx`, ou o fim do texto se `idx` estourar."""
    return posicoes[idx] if idx < len(posicoes) else len_texto


def _idx_pagina_de_pos(posicoes: list[int], pos: int) -> int:
    """Índice (0-based) da página que contém a posição de caractere `pos`."""
    resultado = 0
    for i, ppos in enumerate(posicoes):
        if ppos <= pos:
            resultado = i
        else:
            break
    return resultado


def _avancar_apos_bloco(
    texto_completo: str,
    resultado: dict,
    posicoes: list[int],
    pos_antes_do_bloco: int,
    total_paginas: int,
    len_texto: int,
) -> tuple[int, int]:
    """
    Determina a nova posição do ponteiro após um bloco identificado.

    Cascata de fallback (do mais preciso ao mais grosseiro):
      1. Logo após `offset_fim` (caso normal).
      2. Logo após `offset_inicio` — progresso mínimo dentro da mesma página,
         evitando pular blocos curtos que seguem o bloco identificado.
      3. Início da página seguinte a `pagina_fim` — último recurso quando
         nenhuma âncora é localizada.

    Retorna `(pos_atual, idx_pag_atual)`.
    """
    # Fallback 0 (normal): após offset_fim
    nova_pos = avancar_por_offset(texto_completo, resultado.get("offset_fim", ""), pos_antes_do_bloco)
    if nova_pos != -1:
        return nova_pos, _idx_pagina_de_pos(posicoes, nova_pos)

    # Fallback 1: após offset_inicio
    pos_apos_inicio = avancar_por_offset(
        texto_completo, resultado.get("offset_inicio", ""), pos_antes_do_bloco
    )
    if pos_apos_inicio != -1:
        print("  ⚠  offset_fim não localizado. Avançando para após offset_inicio.")
        return pos_apos_inicio, _idx_pagina_de_pos(posicoes, pos_apos_inicio)

    # Fallback 2: página seguinte a pagina_fim.
    # Página K está no índice K-1, logo a página seguinte a `pagina_fim` está
    # no índice `pagina_fim`.
    pag_fim_resultado = resultado.get("pagina_fim", 0)
    print(
        f"  ⚠  offset_fim e offset_inicio não localizados. "
        f"Avançando até após a pág. {pag_fim_resultado}."
    )
    idx_apos_bloco = pag_fim_resultado
    if 0 < idx_apos_bloco < total_paginas:
        return posicoes[idx_apos_bloco], idx_apos_bloco
    return len_texto, total_paginas


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
    """
    texto_completo = montar_texto_completo(paginas)
    total_paginas  = len(paginas)
    posicoes       = _mapear_paginas(texto_completo, total_paginas)
    len_texto      = len(texto_completo)

    blocos        = []
    pos_atual     = 0       # ponteiro de char no texto_completo
    idx_pag_atual = 0       # índice 0-based da página atual (página = idx + 1)
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
        pos_fim_jan  = _pos_de_idx(posicoes, idx_pag_fim, len_texto)
        janela_texto = _montar_janela(texto_completo, posicoes, idx_pag_atual, pos_atual, pos_fim_jan)

        if not janela_texto.strip():
            print("  ⚠  Janela vazia — fim do documento alcançado.")
            break

        # Página K está no índice K-1: a janela cobre as páginas
        # (idx_pag_atual + 1) até idx_pag_fim.
        print(
            f"── Iteração {iteracao:>3} │ págs. {idx_pag_atual + 1}–{idx_pag_fim} "
            f"│ {len(janela_texto):>8,} chars ──"
        )

        # ── Chama o LLM ───────────────────────────────────────────────────
        resultado = _chamar_llm(config, janela_texto, model, verboso)
        print(resultado)

        # ── Bloco não encontrado — avança 1 página e continua ────────────
        if not resultado.get("classificacao"):
            print("  ⚠  Nenhum bloco identificado. Avançando 1 página...")
            idx_pag_atual = min(idx_pag_atual + 1, total_paginas)
            pos_atual = _pos_de_idx(posicoes, idx_pag_atual, len_texto)
            continue

        # ── Verificação de truncamento ─────────────────────────────────────
        # A última página da janela tem número `idx_pag_fim` (página = índice+1).
        # Se pagina_fim bate com ela, o bloco pode ter sido cortado: expande a
        # janela e tenta de novo.
        if resultado.get("pagina_fim", 0) >= idx_pag_fim and idx_pag_fim < total_paginas:
            janela_expandida = min(janela_paginas * 2, total_paginas - idx_pag_atual)
            print(
                f"  ⚠  Bloco pode estar truncado (pagina_fim={resultado.get('pagina_fim')} "
                f"= última pág. da janela). Expandindo para {janela_expandida} págs..."
            )
            idx_pag_fim_exp  = min(idx_pag_atual + janela_expandida, total_paginas)
            pos_fim_jan_exp  = _pos_de_idx(posicoes, idx_pag_fim_exp, len_texto)
            resultado = _chamar_llm(config, texto_completo[pos_atual:pos_fim_jan_exp], model, verboso)

            if not resultado.get("classificacao"):
                print("  ⚠  Ainda sem bloco após expansão. Avançando meia janela.")
                idx_pag_atual = min(idx_pag_atual + max(1, janela_paginas // 2), total_paginas)
                pos_atual     = _pos_de_idx(posicoes, idx_pag_atual, len_texto)
                continue

        # ── Avança posição para depois do bloco ───────────────────────────
        pos_antes_do_bloco = pos_atual
        pos_atual, idx_pag_atual = _avancar_apos_bloco(
            texto_completo, resultado, posicoes, pos_antes_do_bloco,
            total_paginas, len_texto,
        )

        # ── Extrai o trecho completo do documento original ────────────────
        # pos_busca_inicio aponta para antes do início da janela atual,
        # evitando que o match recaia sobre uma ocorrência anterior idêntica.
        resultado["texto"] = extrair_trecho(
            texto_completo,
            resultado.get("offset_inicio", ""),
            resultado.get("offset_fim", ""),
            pos_busca_inicio=pos_antes_do_bloco,
        )

        # ── Registra o bloco ───────────────────────────────────────────────
        blocos.append(resultado)

        pct = pos_atual / len_texto * 100
        print(
            f"  ✓ Bloco {len(blocos):>3}: [{resultado.get('classificacao', '?')}] "
            f"{resultado.get('titulo', 'N/A')}\n"
            f"           págs. {resultado.get('pagina_inicio', '?')}–{resultado.get('pagina_fim', '?')} │ "
            f"nova pos = char {pos_atual:,} ({pct:.1f}% do doc)"
        )

    print(f"\n{SEP}")
    print(f"  Concluído: {len(blocos)} bloco(s) em {iteracao} iteração(ões).")
    print(f"{SEP}\n")

    return blocos
