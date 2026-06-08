"""
Gera um relatório PDF consolidando:
  1. Resultados da avaliação dos 22 documentos da Seção 1 do DOU
     (segmentação com gpt-5.4-2026-03-05).
  2. Análise da causa principal da baixa precisão (over-segmentation).
  3. Documentação do pipeline de segmentação atual (para rastreamento).

Saída: out/dou/relatorio_precisao_sec1.pdf
"""

import json
import glob
import statistics as st
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable,
)

BASE = Path(__file__).resolve().parent
REL_DIR = BASE / "out" / "dou" / "relatorios"
OUT_PDF = BASE / "out" / "dou" / "relatorio_precisao_sec1.pdf"
CHART = BASE / "out" / "dou" / "_chart_precisao_sec1.png"

# ── Cores do tema ────────────────────────────────────────────────────────────
AZUL = colors.HexColor("#1a3c6e")
AZUL_CLARO = colors.HexColor("#2e5e9e")
CINZA = colors.HexColor("#444444")
CINZA_CLARO = colors.HexColor("#eef2f7")
VERDE = colors.HexColor("#2e7d32")
VERMELHO = colors.HexColor("#c62828")

# ── Carrega métricas ─────────────────────────────────────────────────────────
def carregar_dados():
    rows = []
    for f in sorted(glob.glob(str(REL_DIR / "dou_sec1_*_relatorio.json"))):
        d = json.load(open(f, encoding="utf-8"))
        name = Path(f).name.replace("_relatorio.json", "").replace("dou_sec1_", "")
        det = d["deteccao"]
        q = d["qualidade_texto"]
        c = d["configuracao"]
        rows.append({
            "doc": name,
            "pred": c["total_preditos"],
            "ref": c["total_referencias"],
            "tp": det["TP"], "fp": det["FP"], "fn": det["FN"],
            "p": det["precision"], "r": det["recall"], "f1": det["f1"],
            "wf1": q["word_f1_media"], "cf1": q["char_f1_media"],
        })
    return rows


def gerar_grafico(rows):
    docs = [r["doc"] for r in rows]
    p = [r["p"] for r in rows]
    rec = [r["r"] for r in rows]
    f1 = [r["f1"] for r in rows]
    x = range(len(docs))
    w = 0.27
    fig, ax = plt.subplots(figsize=(11, 4.3))
    ax.bar([i - w for i in x], p, w, label="Precisão", color="#c62828")
    ax.bar(list(x), rec, w, label="Recall", color="#2e7d32")
    ax.bar([i + w for i in x], f1, w, label="F1", color="#1a3c6e")
    ax.set_xticks(list(x))
    ax.set_xticklabels(docs, rotation=60, ha="right", fontsize=7)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("Métrica (0–1)")
    ax.set_title("Detecção por documento — Seção 1 (gpt-5.4-2026-03-05)", fontsize=11)
    ax.legend(loc="upper right", fontsize=8, ncol=3)
    ax.grid(axis="y", alpha=0.3)
    ax.axhline(st.mean(p), color="#c62828", ls="--", lw=0.8, alpha=0.6)
    fig.tight_layout()
    fig.savefig(CHART, dpi=150)
    plt.close(fig)


# ── Estilos ──────────────────────────────────────────────────────────────────
def estilos():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("TituloCapa", parent=s["Title"], fontSize=24,
                         textColor=AZUL, spaceAfter=6, leading=28))
    s.add(ParagraphStyle("SubCapa", parent=s["Normal"], fontSize=12,
                         textColor=CINZA, alignment=TA_CENTER, spaceAfter=4))
    s.add(ParagraphStyle("H1", parent=s["Heading1"], fontSize=15,
                         textColor=AZUL, spaceBefore=14, spaceAfter=6))
    s.add(ParagraphStyle("H2", parent=s["Heading2"], fontSize=12,
                         textColor=AZUL_CLARO, spaceBefore=10, spaceAfter=4))
    s.add(ParagraphStyle("Corpo", parent=s["Normal"], fontSize=9.5,
                         alignment=TA_JUSTIFY, leading=14, spaceAfter=6))
    s.add(ParagraphStyle("Item", parent=s["Normal"], fontSize=9.5,
                         leading=14, leftIndent=14, spaceAfter=3, bulletIndent=4))
    s.add(ParagraphStyle("Nota", parent=s["Normal"], fontSize=8,
                         textColor=CINZA, leading=11))
    s.add(ParagraphStyle("Cod", parent=s["Code"], fontSize=8,
                         textColor=colors.HexColor("#222"), leading=11,
                         backColor=CINZA_CLARO, leftIndent=6, rightIndent=6,
                         spaceBefore=4, spaceAfter=6, borderPadding=6))
    return s


def main():
    rows = carregar_dados()
    gerar_grafico(rows)
    S = estilos()
    story = []

    avg_p = st.mean(r["p"] for r in rows)
    avg_r = st.mean(r["r"] for r in rows)
    avg_f1 = st.mean(r["f1"] for r in rows)
    avg_wf1 = st.mean(r["wf1"] for r in rows)
    avg_cf1 = st.mean(r["cf1"] for r in rows)
    tot_pred = sum(r["pred"] for r in rows)
    tot_ref = sum(r["ref"] for r in rows)

    # ── CAPA ──────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 3.5 * cm))
    story.append(Paragraph("Segmentação Semântica do DOU", S["TituloCapa"]))
    story.append(Paragraph("Seção 1 — Avaliação e Análise de Precisão", S["SubCapa"]))
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="60%", color=AZUL, thickness=1.2))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("Modelo: <b>gpt-5.4-2026-03-05</b>", S["SubCapa"]))
    story.append(Paragraph("22 documentos &middot; threshold de avaliação = 0,5", S["SubCapa"]))
    story.append(Paragraph("Projeto IComp/UFAM &times; JusBrasil", S["SubCapa"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Gerado em 08/06/2026", S["SubCapa"]))
    story.append(PageBreak())

    # ── 1. RESUMO EXECUTIVO ──────────────────────────────────────────────────
    story.append(Paragraph("1. Resumo Executivo", S["H1"]))
    story.append(Paragraph(
        "Os 22 documentos da Seção 1 do Diário Oficial da União foram reprocessados "
        "com o modelo <b>gpt-5.4-2026-03-05</b> e avaliados com o script "
        "<font face='Courier'>avaliar.py</font> contra as anotações de referência "
        "produzidas pelo scraper. A tabela abaixo resume as médias obtidas.", S["Corpo"]))

    resumo = [
        ["Métrica", "Valor médio", "Interpretação"],
        ["Precisão (detecção)", f"{avg_p:.3f}", "Baixa — blocos preditos em excesso"],
        ["Recall (detecção)", f"{avg_r:.3f}", "Alta — quase toda referência é encontrada"],
        ["F1 (detecção)", f"{avg_f1:.3f}", "Limitada pela precisão"],
        ["Word F1 (qualidade)", f"{avg_wf1:.3f}", "Alta — texto extraído é fiel"],
        ["Char F1 (qualidade)", f"{avg_cf1:.3f}", "Alta — texto extraído é fiel"],
    ]
    t = Table(resumo, colWidths=[4.5 * cm, 3 * cm, 8.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(
        f"<b>Conclusão principal:</b> a precisão média é baixa (<b>{avg_p:.3f}</b>) "
        f"enquanto o recall (<b>{avg_r:.3f}</b>) e a qualidade do texto "
        f"(<b>~{avg_cf1:.2f}</b>) são altos. Isso indica que o conteúdo é extraído "
        "corretamente, mas o pipeline produz blocos em excesso — um problema de "
        "<b>granularidade (over-segmentation)</b>, detalhado na Seção 3. Ao todo "
        f"foram gerados <b>{tot_pred:,}</b> blocos preditos contra <b>{tot_ref:,}</b> "
        "blocos de referência (≈1,55&times;).".replace(",", "."), S["Corpo"]))

    story.append(Image(str(CHART), width=17 * cm, height=6.6 * cm))
    story.append(Paragraph(
        "Figura 1 — Precisão, recall e F1 por documento. A linha tracejada marca a "
        "precisão média. Note o padrão consistente: recall alto, precisão baixa.",
        S["Nota"]))
    story.append(PageBreak())

    # ── 2. RESULTADOS DETALHADOS ─────────────────────────────────────────────
    story.append(Paragraph("2. Resultados por Documento", S["H1"]))
    story.append(Paragraph(
        "Cada linha corresponde a uma edição da Seção 1. <b>Pred</b> = blocos "
        "preditos; <b>Ref</b> = blocos de referência; <b>TP/FP/FN</b> = verdadeiros "
        "positivos / falsos positivos / falsos negativos da detecção.", S["Corpo"]))

    header = ["Documento", "Pred", "Ref", "TP", "FP", "FN", "P", "R", "F1", "wF1", "cF1"]
    data = [header]
    for r in rows:
        data.append([
            r["doc"], r["pred"], r["ref"], r["tp"], r["fp"], r["fn"],
            f"{r['p']:.3f}", f"{r['r']:.3f}", f"{r['f1']:.3f}",
            f"{r['wf1']:.3f}", f"{r['cf1']:.3f}",
        ])
    data.append(["MÉDIA", f"{tot_pred}", f"{tot_ref}", "", "", "",
                 f"{avg_p:.3f}", f"{avg_r:.3f}", f"{avg_f1:.3f}",
                 f"{avg_wf1:.3f}", f"{avg_cf1:.3f}"])

    col_w = [3.0 * cm] + [1.05 * cm] * 5 + [1.2 * cm] * 5
    t = Table(data, colWidths=col_w, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dbe5f1")),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, CINZA_CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#bbbbbb")),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    # Destaca em vermelho as precisões < 0,5
    for i, r in enumerate(rows, start=1):
        if r["p"] < 0.5:
            style.append(("TEXTCOLOR", (6, i), (6, i), VERMELHO))
            style.append(("FONTNAME", (6, i), (6, i), "Helvetica-Bold"))
    t.setStyle(TableStyle(style))
    story.append(t)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Valores de precisão em <font color='#c62828'>vermelho</font> indicam P &lt; 0,5. "
        "Os piores casos (06-03, 14-01, 22-01, 11-03, 26-03) são justamente as edições "
        "com muitos atos seriados de texto repetitivo.", S["Nota"]))
    story.append(PageBreak())

    # ── 3. ANÁLISE DA BAIXA PRECISÃO ─────────────────────────────────────────
    story.append(Paragraph("3. Análise da Causa Principal da Baixa Precisão", S["H1"]))
    story.append(Paragraph(
        "<b>Causa raiz: over-segmentation (incompatibilidade de granularidade)</b> "
        "— e não alucinação de conteúdo. A evidência é consistente em todos os "
        "documentos.", S["Corpo"]))

    story.append(Paragraph("3.1. O modelo gera ~2× mais blocos, cada um ~½ do tamanho — com o mesmo conteúdo total", S["H2"]))
    story.append(Paragraph(
        "Tomando <font face='Courier'>dou_sec1_22-01</font> (precisão 0,40) como caso "
        "mais claro:", S["Corpo"]))
    comp = [
        ["", "Referência (gold)", "Predito (gpt-5.4)"],
        ["Nº de blocos", "185", "424  (2,3×)"],
        ["Total de palavras", "120.449", "116.255  (≈ igual)"],
        ["Tamanho mediano do bloco", "256 palavras", "115 palavras  (≈ metade)"],
    ]
    t = Table(comp, colWidths=[6 * cm, 5 * cm, 5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLARO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "O texto total extraído coincide quase exatamente com o gold (116k vs 120k "
        "palavras): o modelo <b>não inventa conteúdo</b>. Ele corta o <i>mesmo</i> "
        "texto em cerca do dobro de pedaços, cada um com metade do tamanho. O "
        "documento 06-03 mostra o mesmo padrão (277 preditos vs 142 referências).",
        S["Corpo"]))

    story.append(Paragraph("3.2. Os falsos positivos são fragmentos reais de publicações, não lixo", S["H2"]))
    story.append(Paragraph(
        "Classificando cada FP pela melhor sobreposição (word_f1) com qualquer "
        "referência:", S["Corpo"]))
    fp_tab = [
        ["Tipo de falso positivo", "06-03", "22-01", "14-01"],
        ["Fragmento de uma ref (≥0,5, perdeu o matching)", "1,8%", "15,8%", "2,3%"],
        ["Pedaço parcial de uma ref (0,2–0,5)", "90,8%", "75,9%", "94,6%"],
        ["Espúrio / fora do gold (<0,2)", "7,4%", "8,3%", "3,1%"],
    ]
    t = Table(fp_tab, colWidths=[8.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), AZUL_CLARO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, CINZA_CLARO]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#bbbbbb")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (1, 2), (-1, 2), colors.HexColor("#fde9e9")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "76–95% dos FPs são <b>sobreposições parciais</b> — pedaços genuínos de "
        "publicações reais que não capturaram o suficiente de uma única publicação "
        "para passar do limiar de 0,5. Apenas 3–8% são conteúdo realmente espúrio "
        "(tabelas, cabeçalhos).", S["Corpo"]))

    story.append(Paragraph("3.3. Por que isso derruba mecanicamente a precisão", S["H2"]))
    story.append(Paragraph(
        "O <font face='Courier'>avaliar.py</font> usa <b>matching guloso 1:1 com "
        "word_f1 ≥ 0,5</b>: cada referência só pode ser reivindicada por um bloco "
        "predito. Então, quando o modelo divide uma publicação do gold em 3 blocos:",
        S["Corpo"]))
    for b in [
        "o melhor pedaço casa &rarr; 1 TP;",
        "os outros 2 pedaços &rarr; <b>2 FPs automáticos</b>, mesmo sendo texto correto.",
    ]:
        story.append(Paragraph(f"&bull; {b}", S["Item"]))
    story.append(Paragraph(
        "Em 06-03, 32% das referências são tocadas por mais de um bloco predito. "
        "Quando a divisão é <i>uniforme</i>, nenhum pedaço chega a 0,5 — o que "
        "ocasionalmente também reduz o recall.", S["Corpo"]))

    story.append(Paragraph("3.4. Fator agravante: atos seriados com muito texto-padrão (boilerplate)", S["H2"]))
    story.append(Paragraph(
        "Os piores documentos são os repletos de atos curtos quase idênticos — "
        "<i>portarias</i> de radiodifusão (22-01), <i>ADIs</i> do STF (06-03), "
        "<i>alvarás</i> da ANM (11-03). Seu texto é ~80% boilerplate compartilhado "
        "(ex.: <font face='Courier' size='7'>\"O DIRETOR DO DEPARTAMENTO... observados "
        "os critérios e parâmetros estabelecidos pelas Portarias de Consolidação "
        "GM/MCOM nº 01/2023...\"</font>). O modelo divide esses atos agressivamente em "
        "um bloco minúsculo por item, e a similaridade do boilerplate ainda gera "
        "confusão de correspondência. São exatamente as edições com precisão abaixo "
        "de 0,45.", S["Corpo"]))

    story.append(Paragraph("3.5. Recomendações (em ordem de impacto provável)", S["H2"]))
    recs = [
        "<b>Calibrar a granularidade no <font face='Courier'>pub.yaml</font></b> — a "
        "definição de bloco está mais fina que a do gold. É a causa raiz e o ajuste "
        "de maior alavancagem.",
        "<b>Reforçar o agrupamento de listas</b> — a pré-detecção "
        "<font face='Courier'>--min-itens-lista</font> (padrão 4) deveria fundir "
        "sequências de cabeçalhos do mesmo tipo, mas não está colapsando as séries de "
        "portarias/ADIs/alvarás. Reduzir o limiar ou torná-lo sensível a itens "
        "boilerplate-similares ajudaria os piores documentos.",
        "<b>Validação do lado da avaliação</b> — considerar uma variante de matching "
        "muitos-para-um no <font face='Courier'>avaliar.py</font> para que fragmentos "
        "corretamente divididos de uma referência não sejam todos penalizados; isso "
        "mede quanto da \"baixa precisão\" é erro real vs. artefato de pontuação.",
    ]
    for i, rtext in enumerate(recs, 1):
        story.append(Paragraph(f"{i}. {rtext}", S["Item"]))
    story.append(PageBreak())

    # ── 4. PIPELINE DE SEGMENTAÇÃO (RASTREAMENTO) ────────────────────────────
    story.append(Paragraph("4. Pipeline de Segmentação Atual (para rastreamento)", S["H1"]))
    story.append(Paragraph(
        "O projeto é composto por três módulos sequenciais e independentemente "
        "executáveis:", S["Corpo"]))
    story.append(Paragraph(
        "scraper/ &rarr; text_extraction/ &rarr; semantic_seg/", S["Cod"]))

    story.append(Paragraph("4.1. Módulo 1 — scraper/", S["H2"]))
    story.append(Paragraph(
        "<font face='Courier'>pub_scrapper.py</font>: um driver Selenium coleta todos "
        "os links de publicações e os cookies de sessão; em seguida um cliente "
        "<font face='Courier'>httpx</font> assíncrono (até 20 conexões simultâneas) "
        "baixa as publicações. Bloqueios 403 persistentes recorrem a um pool de 3 "
        "drivers Selenium. <font face='Courier'>dou_html_parser.py</font> extrai o "
        "texto das tags <font face='Courier'>&lt;p&gt;</font> dentro de "
        "<font face='Courier'>&lt;div class=\"texto-dou\"&gt;</font>. <b>Saída:</b> "
        "<font face='Courier'>Pub_N.txt</font> — usado como <b>anotação de "
        "referência</b> na avaliação. <i>Limitação conhecida: tabelas em HTML não são "
        "capturadas.</i>", S["Corpo"]))

    story.append(Paragraph("4.2. Módulo 2 — text_extraction/", S["H2"]))
    story.append(Paragraph(
        "<font face='Courier'>pdf_extract.py</font>: lê a camada de texto nativa dos "
        "PDFs (sem OCR, sem ML, sem API). Três estratégias selecionadas no import: "
        "(1) <b>pymupdf4llm</b> (preferida, detecção automática de colunas/tabelas "
        "&rarr; Markdown); (2) <b>PyMuPDF blocks + ordenação por coluna</b> "
        "(fallback heurístico); (3) <b>get_text() puro</b> (último recurso). Suporta "
        "extração paralela (<font face='Courier'>--workers N</font>) e avisa em "
        "páginas com menos de 100 caracteres (provável página escaneada). <b>Saída:</b> "
        "<font face='Courier'>page_NNNN.md</font> por página — entrada do Módulo 3.",
        S["Corpo"]))

    story.append(Paragraph("4.3. Módulo 3 — semantic_seg/ (núcleo deste relatório)", S["H2"]))
    story.append(Paragraph(
        "Estratégia de <b>janela deslizante</b> sobre o texto paginado, orquestrada por:",
        S["Corpo"]))
    for b in [
        "<font face='Courier'>main.py</font> — CLI que conecta config, páginas e o "
        "pipeline.",
        "<font face='Courier'>utils_files.py</font> — carrega os "
        "<font face='Courier'>.md</font> ordenados por nome, monta o texto completo e "
        "fatia a janela reinjetando o cabeçalho de página.",
        "<font face='Courier'>utils_llm.py</font> — pipeline central. Constrói "
        "<font face='Courier'>texto_completo</font> uma vez com marcadores "
        "<font face='Courier'>&lt;!-- PÁGINA N --&gt;</font>; avança um ponteiro de "
        "posição (<font face='Courier'>pos_atual</font>) após cada bloco usando "
        "âncoras <font face='Courier'>offset_fim</font>. Expande a janela "
        "automaticamente (até 2×) se um bloco parecer truncado. O matching tolerante "
        "de âncoras (<font face='Courier'>_localizar_ancora</font>) lida com ruído de "
        "markdown, espaços, acentos e variações de caixa em 4 camadas de fallback.",
        "<font face='Courier'>pub.yaml</font> — define tipo de documento, definição "
        "de bloco, regras de granularidade e categorias, injetadas no prompt. O "
        "template do prompt em <font face='Courier'>construir_prompt()</font> é "
        "genérico; toda regra específica do documento vive no YAML.",
    ]:
        story.append(Paragraph(f"&bull; {b}", S["Item"]))

    story.append(Paragraph("4.4. Avaliação — avaliar.py", S["H2"]))
    story.append(Paragraph(
        "Faz <b>matching guloso</b> (maior <font face='Courier'>word_f1</font> "
        "primeiro), 1:1 entre blocos preditos e arquivos de referência. Um predito é "
        "TP se casar com alguma referência com <font face='Courier'>word_f1 ≥ "
        "threshold</font> (0,5). Reporta Precisão/Recall/F1 da detecção e "
        "<font face='Courier'>word_f1</font>/<font face='Courier'>char_f1</font> médios "
        "da qualidade do texto dos TPs.", S["Corpo"]))

    story.append(Paragraph("4.5. Configuração exata desta execução", S["H2"]))
    story.append(Paragraph(
        "Os 22 documentos da Seção 1 foram processados sequencialmente com o comando "
        "(por documento):", S["Corpo"]))
    story.append(Paragraph(
        "python main.py \\<br/>"
        "&nbsp;&nbsp;--config pub.yaml \\<br/>"
        "&nbsp;&nbsp;--diretorio ../text_extraction/out/dou/&lt;doc&gt; \\<br/>"
        "&nbsp;&nbsp;--saida out/dou/blocos/&lt;doc&gt;.json \\<br/>"
        "&nbsp;&nbsp;--model gpt-5.4-2026-03-05 \\<br/>"
        "&nbsp;&nbsp;--janela-paginas 10", S["Cod"]))
    story.append(Paragraph(
        "Avaliação (por documento):", S["Corpo"]))
    story.append(Paragraph(
        "python avaliar.py \\<br/>"
        "&nbsp;&nbsp;--resultado out/dou/blocos/&lt;doc&gt;.json \\<br/>"
        "&nbsp;&nbsp;--anotacoes ../scraper/pubs_extracted/&lt;doc&gt; \\<br/>"
        "&nbsp;&nbsp;--threshold 0.5 \\<br/>"
        "&nbsp;&nbsp;--relatorio out/dou/relatorios/&lt;doc&gt;_relatorio.json", S["Cod"]))
    story.append(Paragraph(
        "<b>Nota de rastreamento:</b> os arquivos de saída não registram o modelo "
        "utilizado. Esta execução foi a primeira a usar <font face='Courier'>"
        "gpt-5.4-2026-03-05</font> em toda a Seção 1; o documento 05-03 falhou uma vez "
        "por erro transitório de conexão (APIConnectionError) e foi reprocessado com "
        "sucesso.", S["Nota"]))

    # ── Rodapé com numeração ─────────────────────────────────────────────────
    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(2 * cm, 1.1 * cm,
                          "Segmentação Semântica do DOU — Seção 1 — gpt-5.4-2026-03-05")
        canvas.drawRightString(A4[0] - 2 * cm, 1.1 * cm, f"Página {doc.page}")
        canvas.setStrokeColor(colors.HexColor("#cccccc"))
        canvas.line(2 * cm, 1.4 * cm, A4[0] - 2 * cm, 1.4 * cm)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(OUT_PDF), pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=1.8 * cm,
        title="Segmentacao Semantica do DOU - Secao 1",
        author="Pipeline semantic_seg",
    )
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    print(f"PDF gerado: {OUT_PDF}")


if __name__ == "__main__":
    main()
