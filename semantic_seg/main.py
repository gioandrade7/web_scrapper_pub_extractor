import json
import argparse
from utils_llm import processar_documento_completo, exibir_resultado, exibir_resumo_blocos
from utils_files import carregar_config, carregar_paginas



def main():
    parser = argparse.ArgumentParser(
        description=(
            "Identifica todos os blocos semânticos de um documento do DOU paginado "
            "via estratégia de janela deslizante."
        )
    )
    parser.add_argument("--config",        required=True,        help="Caminho para o arquivo de configuração JSON.")
    parser.add_argument("--diretorio",     required=True,        help="Diretório com os arquivos de página do documento.")
    parser.add_argument("--extensao",      default=".md",        help="Extensão dos arquivos de página (padrão: .md).")
    parser.add_argument("--saida",         default=None,         help="Caminho para salvar o resultado completo em JSON.")
    parser.add_argument("--model",         default="gpt-5.4-2026-03-05",     help="Modelo OpenAI a utilizar.")
    parser.add_argument("--janela-paginas",default=10, type=int, help="Número de páginas por janela de contexto (padrão: 20).")
    parser.add_argument("--so-resultado",  action="store_true",  help="Exibe apenas os resultados, sem prompts.")
    parser.add_argument(
        "--min-itens-lista",
        default=4,
        type=int,
        help=(
            "Número mínimo de cabeçalhos do mesmo tipo em sequência para marcar "
            "um trecho como lista na pré-detecção (padrão: 4)."
        ),
    )
    parser.add_argument(
        "--sem-pre-deteccao",
        action="store_true",
        help="Desativa a pré-detecção de listas antes da chamada do LLM.",
    )
    args = parser.parse_args()

    # ── Carregamento ──────────────────────────────────────────────────────────
    config  = carregar_config(args.config)
    paginas = carregar_paginas(args.diretorio, extensao=args.extensao)

    # ── Pré-detecção de listas ────────────────────────────────────────────────
    # Marca trechos com várias linhas começando pelo mesmo padrão de cabeçalho
    # (ex.: várias "ACÓRDÃO Nº ..." em sequência) para dar contexto explícito
    # ao LLM e mitigar o colapso de listas em um único bloco semântico.

    # ── Pipeline de janela deslizante ─────────────────────────────────────────
    blocos = processar_documento_completo(
        config,
        paginas,
        model=args.model,
        verboso=not args.so_resultado,
        janela_paginas=args.janela_paginas,
    )

    # ── Exibição ──────────────────────────────────────────────────────────────
    for bloco in blocos:
        exibir_resultado(bloco)

    exibir_resumo_blocos(blocos)

    # ── Persistência ──────────────────────────────────────────────────────────
    if args.saida:
        with open(args.saida, "w", encoding="utf-8") as f:
            json.dump(blocos, f, indent=2, ensure_ascii=False)
        print(f"Resultado salvo em: {args.saida}")


if __name__ == "__main__":
    main()