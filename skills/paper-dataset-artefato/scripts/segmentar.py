#!/usr/bin/env python3
"""
segmentar.py — Ponto de entrada da skill "paper-dataset-artefato".

Wrapper fino sobre o pipeline de segmentação semântica de `semantic_seg/`:
carrega `assets/config.yaml` (gerado por `skill_generator/`) e roda a mesma
janela deslizante usada pelo pipeline principal.

Gerado automaticamente — não editar os campos de config aqui; edite
`../assets/config.yaml`.
"""

import json
import argparse
import sys
from pathlib import Path

_RAIZ_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_RAIZ_REPO / "semantic_seg"))

from utils_llm import processar_documento_completo
from utils_files import carregar_config, carregar_paginas
from display import exibir_resultado, exibir_resumo_blocos

_CONFIG_PADRAO = Path(__file__).resolve().parent.parent / "assets" / "config.yaml"


def main():
    parser = argparse.ArgumentParser(
        description='Segmenta documentos do tipo "paper-dataset-artefato" em blocos semânticos.'
    )
    parser.add_argument("--diretorio",     required=True,        help="Diretório com os arquivos de página do documento.")
    parser.add_argument("--config",        default=str(_CONFIG_PADRAO), help="Caminho para o config.yaml (padrão: assets/config.yaml desta skill).")
    parser.add_argument("--extensao",      default=".md",        help="Extensão dos arquivos de página (padrão: .md).")
    parser.add_argument("--saida",         default=None,         help="Caminho para salvar o resultado completo em JSON.")
    parser.add_argument("--model",         default="gpt-5.4-2026-03-05", help="Modelo OpenAI a utilizar.")
    parser.add_argument("--janela-paginas",default=10, type=int, help="Número de páginas por janela de contexto (padrão: 10).")
    parser.add_argument("--so-resultado",  action="store_true",  help="Exibe apenas os resultados, sem prompts.")
    args = parser.parse_args()

    config  = carregar_config(args.config)
    paginas = carregar_paginas(args.diretorio, extensao=args.extensao)

    blocos = processar_documento_completo(
        config,
        paginas,
        model=args.model,
        verboso=not args.so_resultado,
        janela_paginas=args.janela_paginas,
    )

    for bloco in blocos:
        exibir_resultado(bloco)

    exibir_resumo_blocos(blocos)

    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            json.dump(blocos, f, indent=2, ensure_ascii=False)
        print(f"Resultado salvo em: {args.saida}")


if __name__ == "__main__":
    main()
