"""
templates.py — Geração do conteúdo de SKILL.md e scripts/segmentar.py
para uma skill de segmentação semântica.
"""


def gerar_skill_md(nome: str, skill_description: str, tipo_documento: str) -> str:
    return f"""---
name: {nome}
description: {skill_description}
---

# {tipo_documento}

Segmenta documentos do tipo **{tipo_documento}** em blocos semânticos,
classificando cada bloco em uma das categorias definidas em
`assets/config.yaml`.

Esta skill foi gerada automaticamente pelo `skill_generator/` a partir de uma
amostra do documento e das classes de segmento fornecidas pelo usuário. A
lógica de segmentação (janela deslizante, matching de âncoras) é a mesma do
pipeline principal em `semantic_seg/`; apenas a configuração é específica
deste tipo de documento.

## Uso

```bash
python scripts/segmentar.py \\
    --diretorio <diretório com as páginas .md do documento> \\
    --saida resultado.json
```

Parâmetros adicionais (`--model`, `--janela-paginas`, `--extensao`,
`--so-resultado`) — ver `python scripts/segmentar.py --help`.

## Arquivos

- `assets/config.yaml`: definição do tipo de documento, regras de
  granularidade (inclui a definição de bloco) e classes de segmento.
- `scripts/segmentar.py`: wrapper que carrega `assets/config.yaml` e invoca
  o pipeline de segmentação de `semantic_seg/`.
"""


def gerar_segmentar_py(nome: str, model_padrao: str) -> str:
    return f'''#!/usr/bin/env python3
"""
segmentar.py — Ponto de entrada da skill "{nome}".

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
        description='Segmenta documentos do tipo "{nome}" em blocos semânticos.'
    )
    parser.add_argument("--diretorio",     required=True,        help="Diretório com os arquivos de página do documento.")
    parser.add_argument("--config",        default=str(_CONFIG_PADRAO), help="Caminho para o config.yaml (padrão: assets/config.yaml desta skill).")
    parser.add_argument("--extensao",      default=".md",        help="Extensão dos arquivos de página (padrão: .md).")
    parser.add_argument("--saida",         default=None,         help="Caminho para salvar o resultado completo em JSON.")
    parser.add_argument("--model",         default="{model_padrao}", help="Modelo OpenAI a utilizar.")
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
        print(f"Resultado salvo em: {{args.saida}}")


if __name__ == "__main__":
    main()
'''
