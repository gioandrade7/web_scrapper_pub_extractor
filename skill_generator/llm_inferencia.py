"""
llm_inferencia.py — Infere, via LLM, a estrutura de um novo tipo de documento
a partir de uma amostra e das classes de segmento fornecidas pelo usuário.

Único ponto do gerador de skills que chama o modelo. Recebe o texto de uma
amostra (páginas concatenadas, com marcadores `<!-- PÁGINA N -->`, no mesmo
formato usado por `semantic_seg/utils_llm.py`) e a lista de classes já
definida pelo usuário, e devolve os demais campos do config.yaml
(`tipo_documento`, `descricao_geral`, `regras_granularidade`) além da
`description` do SKILL.md.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CAMPOS_ESPERADOS = (
    "tipo_documento",
    "descricao_geral",
    "regras_granularidade",
    "skill_description",
)


def _construir_prompt(texto_amostra: str, segmentos: list[dict]) -> str:
    segmentos_formatados = "\n\n".join(
        f"{i + 1}. **{s['nome']}**\n   {s['descricao'].strip()}"
        for i, s in enumerate(segmentos)
    )

    return f"""Você é um especialista em análise de documentos e em desenho de pipelines de segmentação semântica baseados em LLM.

## Contexto
Você vai gerar a configuração de um novo tipo de documento para um pipeline de segmentação semântica já existente. O pipeline percorre o documento com uma janela deslizante e, a cada chamada, pede ao modelo para identificar **o próximo bloco semântico completo** do texto, classificando-o em uma das categorias abaixo. A configuração que você vai gerar é injetada diretamente no prompt desse pipeline, então cada campo deve ser redigido como instrução direta para esse outro modelo (mesmo estilo e nível de detalhe de um manual de anotação), não como uma descrição para um humano.

## Classes de segmento (definidas pelo usuário — não altere nomes nem descrições)
{segmentos_formatados}

## Amostra do documento (texto real, para você inferir os padrões estruturais)
Pode conter trechos de mais de um documento, cada um precedido por um
marcador `<!-- AMOSTRA i: documento distinto (...) -->`. Quando houver mais
de um marcador desses, trate cada trecho como o início de uma edição/
documento independente (não como continuação um do outro, mesmo que a
numeração de página reinicie em cada um) e baseie os exemplos de
`regras_granularidade` em padrões que se repetem entre eles, não em uma amostra só.
```
{texto_amostra}
```

## Sua tarefa
A partir da amostra acima e das classes fornecidas, infira:

1. `tipo_documento`: rótulo curto e formal do tipo de documento.
2. `descricao_geral`: um parágrafo descrevendo o que é esse tipo de documento e a variedade de conteúdos que abrange. Baseie-se apenas no que é observável ou razoavelmente inferível a partir da amostra.
3. `regras_granularidade`: campo único que define, ao mesmo tempo, o que constitui "um bloco" semântico neste tipo de documento **e** as regras explícitas de quando agrupar vs. separar conteúdo em blocos distintos. **A fronteira do bloco é definida pela mudança de classe de segmento, não pela estrutura editorial do documento por si só.** Antes de escrever este campo, olhe para a natureza das classes de segmento acima.

   **Seja conciso — isto é uma instrução de anotação para outro modelo ler a cada chamada, não um manual exaustivo.** Regras longas demais custam tokens e atenção do modelo em toda janela processada, sem ganho proporcional de precisão. 
4. `skill_description`: 1-2 frases, em terceira pessoa, descrevendo quando esta skill deve ser usada (ex.: "Segmenta publicações da Seção 3 do Diário Oficial da União em blocos por ato administrativo."). Este texto vai para o campo `description` do frontmatter de uma Agent Skill — deve deixar claro o tipo de documento e a tarefa, para que um agente saiba quando ativá-la.

## Formato de resposta
Retorne **exclusivamente** um objeto JSON válido, sem texto adicional, com exatamente estas chaves (todas string):
{json.dumps(CAMPOS_ESPERADOS)}
"""


def inferir_estrutura(
    texto_amostra: str,
    segmentos: list[dict],
    model: str,
) -> dict:
    """
    Chama o LLM para inferir tipo_documento, descricao_geral,
    regras_granularidade e skill_description a partir da amostra e das classes.

    Retorna um dict com exatamente as chaves em `CAMPOS_ESPERADOS`.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)

    prompt = _construir_prompt(texto_amostra, segmentos)

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "Você é um assistente especializado em análise de documentos "
                    "e em desenho de configurações para "
                    "pipelines de segmentação semântica. Responda sempre com um "
                    "único objeto JSON válido, sem texto adicional."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    dados = json.loads(raw)

    faltando = [campo for campo in CAMPOS_ESPERADOS if not dados.get(campo)]
    if faltando:
        raise ValueError(
            f"Resposta do LLM não trouxe os campos obrigatórios: {faltando}. "
            f"Resposta bruta: {raw[:500]}"
        )

    return {campo: dados[campo] for campo in CAMPOS_ESPERADOS}
