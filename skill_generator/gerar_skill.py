#!/usr/bin/env python3
"""
gerar_skill.py — Gera uma skill de segmentação semântica (SKILL.md +
assets/config.yaml + scripts/segmentar.py) a partir de uma amostra de
documento e das classes de segmento fornecidas pelo usuário.

O usuário fornece apenas as classes (`segmentos`: nome + descrição). Todo o
resto do config (`tipo_documento`, `descricao_geral`, `regras_granularidade`
— este último cobrindo tanto a definição de bloco quanto as regras de
agrupar/separar) e a `description` da skill são inferidos por LLM a partir
da amostra.

`--amostra` aceita um ou mais diretórios. Cada um é tratado como um
documento distinto e concatenado com um marcador de separação, o que
permite montar a amostra a partir de vários documentos (ex.: as primeiras
páginas de 3 edições diferentes, via `--paginas-por-amostra 10`) em vez de
um único documento completo.

Uso:
    python gerar_skill.py \\
        --amostra ../text_extraction/out/dou_sec3_10-01 \\
        --classes classes_sec3.yaml \\
        --nome dou-secao3 \\
        --saida ../skills

    # Amostra composta pelo início de 3 documentos diferentes
    python gerar_skill.py \\
        --amostra ../text_extraction/out/dou/dou_sec1_02-01 \\
                  ../text_extraction/out/dou/dou_sec1_06-01 \\
                  ../text_extraction/out/dou/dou_sec1_12-01 \\
        --paginas-por-amostra 10 \\
        --classes classes_sec1.yaml \\
        --nome dou-secao1

    # Sem chamar o LLM (testa a estrutura de arquivos gerada, sem custo de API):
    python gerar_skill.py --amostra ... --classes ... --nome dou-secao3 --dry-run
"""

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from semantic_seg.utils_files import carregar_paginas, montar_texto_completo  # noqa: E402

from llm_inferencia import inferir_estrutura  # noqa: E402
from templates import gerar_skill_md, gerar_segmentar_py  # noqa: E402

MODEL_PADRAO = "gpt-5.4-2026-03-05"
MAX_CHARS_AMOSTRA_PADRAO = 20_000

_PLACEHOLDER_DRY_RUN = {
    "tipo_documento": "[DRY-RUN] tipo_documento não inferido (execução sem LLM)",
    "descricao_geral": "[DRY-RUN] descricao_geral não inferida (execução sem LLM).",
    "regras_granularidade": "[DRY-RUN] regras_granularidade não inferidas (execução sem LLM).",
    "skill_description": "[DRY-RUN] description não inferida (execução sem LLM).",
}


def carregar_segmentos(caminho: Path) -> list[dict]:
    """
    Carrega a lista de classes de segmento fornecida pelo usuário.

    Aceita tanto um arquivo com uma lista no nível raiz quanto um arquivo com
    a chave `segmentos:` (permitindo reaproveitar diretamente a seção
    `segmentos` de um config.yaml existente, como o pub.yaml/lei.yaml).
    """
    with open(caminho, "r", encoding="utf-8") as f:
        dados = yaml.safe_load(f)

    segmentos = dados.get("segmentos", dados) if isinstance(dados, dict) else dados

    if not isinstance(segmentos, list) or not segmentos:
        raise ValueError(
            f"'{caminho}' deve conter uma lista de segmentos (ou uma chave "
            "'segmentos:' com essa lista), cada um com 'nome' e 'descricao'."
        )

    for i, s in enumerate(segmentos):
        if not isinstance(s, dict) or "nome" not in s or "descricao" not in s:
            raise ValueError(
                f"Segmento #{i + 1} em '{caminho}' precisa ter as chaves "
                f"'nome' e 'descricao'. Recebido: {s!r}"
            )

    return segmentos


def carregar_texto_amostra(
    diretorios: list[Path],
    extensao: str,
    max_chars: int,
    paginas_por_amostra: int | None = None,
) -> str:
    """
    Carrega e concatena uma ou mais amostras de documento.

    Cada diretório em `diretorios` é um documento distinto: suas páginas são
    numeradas a partir de 1 (via `carregar_paginas`), então documentos
    diferentes podem ter marcadores `<!-- PÁGINA N -->` repetidos. Por isso
    cada bloco de amostra é precedido por um marcador `<!-- AMOSTRA i -->`
    explícito, deixando claro ao LLM que se trata de um documento novo, não
    da continuação do anterior.

    Se `paginas_por_amostra` for informado, usa apenas as N primeiras
    páginas de cada diretório (ex.: amostrar só o início de vários
    documentos, em vez de um documento completo).

    `max_chars` é dividido em partes iguais entre os documentos (em vez de
    truncar a concatenação final), para que um truncamento não elimine
    inteiramente os últimos documentos da lista.
    """
    orcamento_por_doc = max_chars // len(diretorios)

    partes = []
    for i, diretorio in enumerate(diretorios, start=1):
        paginas = carregar_paginas(str(diretorio), extensao=extensao)
        if paginas_por_amostra is not None:
            paginas = paginas[:paginas_por_amostra]
        texto_doc = montar_texto_completo(paginas)
        if len(texto_doc) > orcamento_por_doc:
            print(
                f"  ⚠  Amostra {i} ({diretorio.name}) tem {len(texto_doc):,} chars, "
                f"truncando para {orcamento_por_doc:,} chars (orçamento por "
                f"documento dentro de --max-chars-amostra)."
            )
            texto_doc = texto_doc[:orcamento_por_doc]
        partes.append(f"<!-- AMOSTRA {i}: documento distinto ({diretorio.name}) -->\n{texto_doc}")

    return "\n\n".join(partes)


def montar_config(estrutura: dict, segmentos: list[dict]) -> dict:
    return {
        "tipo_documento": estrutura["tipo_documento"],
        "descricao_geral": estrutura["descricao_geral"],
        "regras_granularidade": estrutura["regras_granularidade"],
        "segmentos": segmentos,
    }


def escrever_skill(saida_base: Path, nome: str, config: dict, skill_description: str, forcar: bool) -> Path:
    skill_dir = saida_base / nome
    if skill_dir.exists() and not forcar:
        raise FileExistsError(
            f"'{skill_dir}' já existe. Use --forcar para sobrescrever."
        )

    assets_dir = skill_dir / "assets"
    scripts_dir = skill_dir / "scripts"
    assets_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    (skill_dir / "SKILL.md").write_text(
        gerar_skill_md(nome, skill_description, config["tipo_documento"]),
        encoding="utf-8",
    )

    with open(assets_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, width=1000)

    (scripts_dir / "segmentar.py").write_text(
        gerar_segmentar_py(nome, MODEL_PADRAO),
        encoding="utf-8",
    )

    return skill_dir


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Gera uma skill de segmentação semântica (SKILL.md + "
            "assets/config.yaml + scripts/segmentar.py) a partir de uma "
            "amostra de documento e das classes fornecidas pelo usuário."
        )
    )
    parser.add_argument("--amostra",  required=True, nargs="+", type=Path, help="Um ou mais diretórios com páginas (.md) de amostra. Cada diretório é tratado como um documento distinto.")
    parser.add_argument("--paginas-por-amostra", default=None, type=int, help="Se informado, usa apenas as N primeiras páginas de cada diretório em --amostra (ex.: amostrar só o início de vários documentos).")
    parser.add_argument("--classes",  required=True, type=Path, help="Arquivo YAML com a lista de segmentos (nome + descricao).")
    parser.add_argument("--nome",     required=True,             help="Nome/slug da skill (nome da pasta gerada em --saida).")
    parser.add_argument("--saida",    default=Path(__file__).resolve().parent.parent / "skills", type=Path, help="Diretório onde a pasta da skill será criada (padrão: ../skills).")
    parser.add_argument("--extensao", default=".md",             help="Extensão dos arquivos de página da amostra (padrão: .md).")
    parser.add_argument("--model",    default=MODEL_PADRAO,      help="Modelo OpenAI usado para inferir a estrutura do documento.")
    parser.add_argument("--max-chars-amostra", default=MAX_CHARS_AMOSTRA_PADRAO, type=int, help="Máximo de caracteres da amostra enviados ao LLM.")
    parser.add_argument("--forcar",   action="store_true",       help="Sobrescreve a skill se a pasta de saída já existir.")
    parser.add_argument("--dry-run",  action="store_true",       help="Não chama o LLM; usa placeholders para testar a estrutura de arquivos gerada.")
    args = parser.parse_args()

    amostras_str = ", ".join(str(a) for a in args.amostra)
    SEP = "═" * 64
    print(f"\n{SEP}")
    print(f"  Gerando skill '{args.nome}' a partir de {len(args.amostra)} amostra(s): {amostras_str}")
    print(f"{SEP}\n")

    segmentos = carregar_segmentos(args.classes)
    print(f"  {len(segmentos)} classe(s) carregada(s) de '{args.classes}'.")

    texto_amostra = carregar_texto_amostra(
        args.amostra, args.extensao, args.max_chars_amostra, args.paginas_por_amostra
    )

    if args.dry_run:
        print("  ⚠  --dry-run: pulando chamada ao LLM, usando placeholders.")
        estrutura = dict(_PLACEHOLDER_DRY_RUN)
    else:
        print(f"  Chamando {args.model} para inferir tipo_documento, descricao_geral "
              f"e regras_granularidade...")
        estrutura = inferir_estrutura(texto_amostra, segmentos, args.model)

    config = montar_config(estrutura, segmentos)
    skill_dir = escrever_skill(args.saida, args.nome, config, estrutura["skill_description"], args.forcar)

    print(f"\n{SEP}")
    print(f"  Skill gerada em: {skill_dir}")
    print(f"    - {skill_dir / 'SKILL.md'}")
    print(f"    - {skill_dir / 'assets' / 'config.yaml'}")
    print(f"    - {skill_dir / 'scripts' / 'segmentar.py'}")
    print(f"{SEP}\n")


if __name__ == "__main__":
    main()
