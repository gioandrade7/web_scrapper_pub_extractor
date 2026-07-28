"""
display.py — Exibição no terminal dos blocos identificados.

Puramente cosmético: nenhuma lógica de pipeline vive aqui.
"""


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
