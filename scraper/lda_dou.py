"""
Exemplo mínimo de LDA aplicado a trechos do DOU (INLABS).

Objetivo: descobrir empiricamente quais tópicos emergem do texto,
antes de decidir entre um esquema top-down (altera/revoga/retifica)
e um esquema bottom-up (data-driven, como no artigo SBBD 2022).

Requisitos: pip install gensim scikit-learn nltk --break-system-packages
"""

import re
import ssl
import nltk

# Contorna problema de certificado SSL no macOS ao baixar dados do NLTK
ssl._create_default_https_context = ssl._create_unverified_context  # noqa: SIM117
from nltk.corpus import stopwords
from gensim import corpora, models
from gensim.models import CoherenceModel

nltk.download("stopwords", quiet=True)
STOPWORDS_PT = set(stopwords.words("portuguese"))

# Palavras de "ruído" comuns em atos administrativos que não carregam
# sentido temático (aparecem em quase todo documento, então não ajudam
# o LDA a diferenciar tópicos). Ajuste conforme observar nos resultados.
RUIDO_ADMINISTRATIVO = {
    "art", "artigo", "lei", "decreto", "portaria", "publicado", "publicação",
    "diário", "oficial", "união", "brasília", "presidente", "república",
    "processo", "nº", "n", "of", "sei",
}


def limpar_texto(texto: str) -> list[str]:
    """Normaliza e tokeniza um trecho de DOU.

    Trata especificamente o problema de letter-spacing observado no
    preâmbulo de leis (ex: "P R E S I D E N T E") — colapsa sequências
    de letras isoladas separadas por espaço antes de tokenizar.
    """
    # Colapsa letter-spacing: "P R E S I D E N T E" -> "PRESIDENTE"
    texto = re.sub(r"\b(?:[A-ZÀ-Ú]\s){2,}[A-ZÀ-Ú]\b",
                    lambda m: m.group(0).replace(" ", ""), texto)
    texto = re.sub(r"<[^>]+>", " ", texto)  # remove tags HTML residuais
    texto = texto.lower()
    tokens = re.findall(r"[a-zà-ú]{3,}", texto)  # só palavras, min 3 letras
    tokens = [t for t in tokens
              if t not in STOPWORDS_PT and t not in RUIDO_ADMINISTRATIVO]
    return tokens


def rodar_lda(trechos: list[str], num_topics: int = 8, passes: int = 10):
    """Roda LDA sobre uma lista de trechos e retorna o modelo + dicionário."""
    docs_tokenizados = [limpar_texto(t) for t in trechos]

    dicionario = corpora.Dictionary(docs_tokenizados)
    # Remove termos muito raros (<5 docs) ou muito frequentes (>50% dos docs)
    dicionario.filter_extremes(no_below=5, no_above=0.5)

    corpus_bow = [dicionario.doc2bow(doc) for doc in docs_tokenizados]

    modelo = models.LdaModel(
        corpus=corpus_bow,
        id2word=dicionario,
        num_topics=num_topics,
        passes=passes,
        random_state=42,
        alpha="auto",
    )

    # Coerência: métrica automática para comparar diferentes valores de k
    coerencia = CoherenceModel(
        model=modelo, texts=docs_tokenizados, dictionary=dicionario,
        coherence="c_v",
    ).get_coherence()

    return modelo, dicionario, corpus_bow, coerencia


def explorar_k(trechos: list[str], valores_k=range(4, 17, 2)):
    """Testa vários valores de k e imprime a coerência de cada um.

    Uso: rode isso primeiro para escolher k antes de interpretar tópicos.
    O artigo SBBD 2022 testou k de 4 a 16.
    """
    resultados = []
    for k in valores_k:
        _, _, _, coerencia = rodar_lda(trechos, num_topics=k, passes=5)
        resultados.append((k, coerencia))
        print(f"k={k:2d}  coerência={coerencia:.4f}")
    return resultados


def imprimir_topicos(modelo, num_palavras: int = 15):
    """Imprime as palavras mais prováveis de cada tópico.

    Este é o passo que exige leitura humana: você olha as palavras
    de cada tópico e decide que rótulo (Lei, Licitação, Pessoal...)
    faz sentido dar a ele.
    """
    for idx, topico in modelo.print_topics(num_words=num_palavras):
        print(f"\n--- Tópico {idx} ---")
        # print_topics retorna string tipo "0.012*'palavra' + 0.008*'outra'"
        pares = re.findall(r'"([^"]+)"|\'([^\']+)\'', topico)
        palavras = [p[0] or p[1] for p in pares]
        print(", ".join(palavras))


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="LDA sobre publicações do DOU scrapeadas."
    )
    parser.add_argument(
        "--raiz",
        type=Path,
        default=Path(__file__).parent / "pubs_extracted",
        help="Raiz com os diretórios de publicações (padrão: pubs_extracted/).",
    )
    parser.add_argument(
        "--filtro",
        default="",
        help="Filtro de subdiretório, ex.: 'sec1' para usar só a Seção 1.",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=None,
        help="Número de tópicos. Se omitido, explora k de 4 a 16 antes de rodar.",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=10,
        help="Número de passes do LDA (padrão: 10).",
    )
    args = parser.parse_args()

    # ── Carrega publicações ────────────────────────────────────────────────────
    trechos = []
    diretorios = sorted(
        d for d in args.raiz.iterdir()
        if d.is_dir() and args.filtro in d.name
    )
    for d in diretorios:
        for pub in sorted(d.glob("Pub_*.txt")):
            texto = pub.read_text(encoding="utf-8").strip()
            if texto:
                trechos.append(texto)

    if not trechos:
        raise SystemExit(f"Nenhuma publicação encontrada em '{args.raiz}' (filtro: '{args.filtro}').")

    print(f"Publicações carregadas: {len(trechos)} de {len(diretorios)} diretório(s)")
    print(f"Filtro: '{args.filtro or '(nenhum)'}'\n")

    # ── Etapa 1: explorar k (se não foi especificado) ─────────────────────────
    if args.k is None:
        print("=== Etapa 1: explorar valores de k (4 a 16) ===")
        explorar_k(trechos, valores_k=range(4, 17, 2))
        print("\nEscolha um k com base na coerência acima e rode com --k <valor>.")
    else:
        # ── Etapa 2: rodar com k escolhido ────────────────────────────────────
        print(f"=== Rodando LDA com k={args.k} ===")
        modelo, dic, corpus, coer = rodar_lda(trechos, num_topics=args.k, passes=args.passes)
        print(f"Coerência final: {coer:.4f}")
        imprimir_topicos(modelo)