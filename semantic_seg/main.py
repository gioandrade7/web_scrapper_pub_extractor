import os
import json
import argparse
from utils_llm import processar_documento_completo
from utils_files import carregar_paginas
from corretor import segmentar_com_correcao
from display import exibir_resultado, exibir_resumo_blocos, exibir_analise



def _caminho_versionado(caminho: str) -> str:
    """
    Devolve um caminho livre, acrescentando `_v2`, `_v3`... se preciso.

    Resultados de rodadas anteriores são material de comparação manual e custam
    chamadas de API para refazer, então nunca são sobrescritos.
    """
    if not os.path.exists(caminho):
        return caminho

    base = caminho.removesuffix(".json")
    versao = 2
    while os.path.exists(f"{base}_v{versao}.json"):
        versao += 1
    return f"{base}_v{versao}.json"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Identifica todos os blocos semânticos (segmentação, sem classificação) "
            "de um documento paginado via estratégia de janela deslizante, com "
            "correção iterativa do prompt a partir da análise dos blocos por um LLM."
        )
    )
    parser.add_argument("--diretorio",     required=True,        help="Diretório com os arquivos de página do documento.")
    parser.add_argument("--extensao",      default=".md",        help="Extensão dos arquivos de página (padrão: .md).")
    parser.add_argument("--saida",         default=None,         help="Caminho para salvar o resultado completo em JSON.")
    parser.add_argument("--model",         default="gpt-5.6-terra",     help="Modelo OpenAI a utilizar.")
    parser.add_argument("--janela-paginas",default=10, type=int, help="Número de páginas por janela de contexto (padrão: 20).")
    parser.add_argument("--max-ciclos",    default=0, type=int,  help="Teto de ciclos de segmentação + correção. 0 (padrão) roda até o analisador aprovar.")
    parser.add_argument("--sem-correcao",  action="store_true",  help="Roda um único ciclo, sem o corretor.")
    parser.add_argument("--so-resultado",  action="store_true",  help="Exibe apenas os resultados, sem prompts.")
    args = parser.parse_args()

    # ── Carregamento ──────────────────────────────────────────────────────────
    paginas = carregar_paginas(args.diretorio, extensao=args.extensao)

    # ── Pipeline de janela deslizante ─────────────────────────────────────────
    historico = []
    if args.sem_correcao:
        blocos = processar_documento_completo(
            paginas,
            model=args.model,
            verboso=not args.so_resultado,
            janela_paginas=args.janela_paginas,
        )
    else:
        blocos, historico = segmentar_com_correcao(
            paginas,
            model=args.model,
            verboso=not args.so_resultado,
            janela_paginas=args.janela_paginas,
            max_ciclos=args.max_ciclos,
            exibir_analise=exibir_analise,
        )

    # ── Exibição ──────────────────────────────────────────────────────────────
    for bloco in blocos:
        exibir_resultado(bloco)

    exibir_resumo_blocos(blocos)

    # ── Persistência ──────────────────────────────────────────────────────────
    # `--saida` guarda apenas a lista de blocos, formato que `avaliar.py` espera.
    # A extração de cada ciclo vai para um arquivo próprio, no mesmo formato, e
    # o rastro da correção (diretrizes, análises) para um arquivo irmão.
    if args.saida:
        caminho = _caminho_versionado(args.saida)
        if caminho != args.saida:
            print(f"'{args.saida}' já existe — preservado.")

        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(blocos, f, indent=2, ensure_ascii=False)
        print(f"Resultado salvo em: {caminho}")

        base = caminho.removesuffix(".json")

        registro = []
        for entrada in historico:
            caminho_ciclo = f"{base}_ciclo{entrada['ciclo']}.json"
            with open(caminho_ciclo, "w", encoding="utf-8") as f:
                json.dump(entrada["blocos"], f, indent=2, ensure_ascii=False)
            print(f"Extração do ciclo {entrada['ciclo']} salva em: {caminho_ciclo}"
                  f" ({entrada['blocos_produzidos']} blocos)")

            registro.append({**{k: v for k, v in entrada.items() if k != "blocos"},
                             "arquivo_blocos": caminho_ciclo})

        if registro:
            caminho_correcao = f"{base}_correcao.json"
            with open(caminho_correcao, "w", encoding="utf-8") as f:
                json.dump(registro, f, indent=2, ensure_ascii=False)
            print(f"Histórico de correção salvo em: {caminho_correcao}")


if __name__ == "__main__":
    main()