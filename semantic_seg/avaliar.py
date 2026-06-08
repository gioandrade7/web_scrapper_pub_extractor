"""
avaliar.py — Avalia o pipeline de extração de blocos semânticos.

Métricas calculadas em dois níveis (DOU e Leis)
────────────────────────────────────────────────
1. DETECÇÃO (nível de bloco)
   Cada arquivo de referência é um bloco que deveria ter sido detectado.
   Um bloco predito é considerado TP se seu texto corresponde a uma
   referência com word_f1 ≥ threshold (padrão 0.5).

   TP  = blocos preditos que casaram com alguma referência
   FP  = blocos preditos que não casaram com nenhuma referência
   FN  = referências que não foram casadas por nenhum bloco

   Precision  = TP / (TP + FP)
   Recall     = TP / (TP + FN)
   F1         = 2 × P × R / (P + R)

2. QUALIDADE DO TEXTO (para os TPs)
   Para cada par casado, calcula char_f1 e word_f1 do texto extraído
   vs. o texto de referência.

3. CLASSIFICAÇÃO — apenas para --formato lei
   Após o matching, verifica se o rótulo predito bate com o rótulo
   anotado extraído do nome do arquivo de referência.
   Gera accuracy global e métricas P/R/F1 por classe.

Uso
───
    # DOU (comportamento original)
    python avaliar.py \
        --resultado resultado.json \
        --anotacoes ./anotacoes \
        [--threshold 0.5] \
        [--relatorio relatorio.json]

    # Leis
    python avaliar.py \
        --formato lei \
        --resultado resultado.json \
        --anotacoes ./dataset3txtLEI/1965/LEI-1965-04719 \
        [--threshold 0.5] \
        [--relatorio relatorio.json]
"""

import json
import re
import argparse
from pathlib import Path
from collections import Counter


# ──────────────────────────────────────────────────────────────────────────────
# Normalização e métricas de texto
# ──────────────────────────────────────────────────────────────────────────────

def normalizar(texto: str) -> str:
    texto = re.sub(r"<!--.*?-->", " ", texto, flags=re.DOTALL)
    texto = re.sub(r"```[a-z]*", " ", texto)
    texto = re.sub(r"^#{1,6}\s+", " ", texto, flags=re.MULTILINE)
    texto = re.sub(r"\*{1,3}|_{1,3}", " ", texto)
    texto = re.sub(r"^\s*>\s*", " ", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*[-*]\s+", " ", texto, flags=re.MULTILINE)
    texto = re.sub(r"^\s*\d+\.\s+", " ", texto, flags=re.MULTILINE)
    texto = texto.replace("№", "nº")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().lower()


def tokenizar_palavras(texto: str) -> Counter:
    return Counter(re.findall(r"[a-záéíóúàâêôãõüç\d]+", texto))


def tokenizar_chars(texto: str) -> Counter:
    return Counter(texto[i:i+2] for i in range(len(texto) - 1))


def _prf(pred: Counter, ref: Counter) -> tuple:
    inter    = sum((pred & ref).values())
    tot_pred = sum(pred.values())
    tot_ref  = sum(ref.values())
    p = inter / tot_pred if tot_pred else 0.0
    r = inter / tot_ref  if tot_ref  else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


def metricas_texto(pred: str, ref: str) -> dict:
    pn, rn = normalizar(pred), normalizar(ref)
    wp, wr, wf = _prf(tokenizar_palavras(pn), tokenizar_palavras(rn))
    cp, cr, cf = _prf(tokenizar_chars(pn),    tokenizar_chars(rn))
    return {
        "word_precision": wp, "word_recall": wr, "word_f1": wf,
        "char_precision": cp, "char_recall": cr, "char_f1": cf,
        "match_exato": pn == rn,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Carregamento de referências
# ──────────────────────────────────────────────────────────────────────────────

def carregar_referencias_dou(dir_anot: Path) -> tuple[dict, dict]:
    """Formato DOU: arquivos Pub_NN.txt. Sem informação de classe."""
    refs = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted(dir_anot.glob("Pub_*.txt"))
    }
    return refs, {}


_PATTERN_LEI = re.compile(r'^\d{5}-(.+)-\d{5}-\d{5}\.txt$')

def _normalizar_classe_lei(label: str) -> str:
    """Extrai o tipo semântico base do rótulo hierárquico do dataset de leis.

    Exemplos:
        art1           → art
        art1_cpt       → cpt
        art1_par1u     → par
        art1_cpt_inc2  → inc
        art3_cpt_alt1  → alt
        art2_par1_pena → pena
        cap3           → cap
    """
    last = label.split("_")[-1]
    if re.match(r'^art\d+(-\d+)?$', last):  return "art"
    if last == "cpt":                        return "cpt"
    if re.match(r'^par\d*u?$', last):        return "par"
    if re.match(r'^inc\d+$', last):          return "inc"
    if re.match(r'^ali\d+$', last):          return "ali"
    if re.match(r'^ite[m]?\d*$', last):      return "item"
    if re.match(r'^alt\d+$', last):          return "alt"
    if re.match(r'^cap\d+$', last):          return "cap"
    if re.match(r'^tit\d+$', last):          return "tit"
    if re.match(r'^sec\d+$', last):          return "sec"
    if re.match(r'^sub\d+$', last):          return "subsec"
    if re.match(r'^liv\d+$', last):          return "liv"
    if re.match(r'^prt\d+$', last):          return "prt"
    if last == "pena":                       return "pena"
    if last in ("epigrafe", "ementa", "preambulo"):
        return last
    return last


def carregar_referencias_lei(dir_anot: Path) -> tuple[dict, dict]:
    """Formato Leis: arquivos {seq}-{classe}-{pag_ini}-{pag_fim}.txt.

    Ignora arquivos vazios (blocos 'art' container sem texto próprio).
    Retorna (refs, classes) onde:
        refs    = {nome_arquivo: texto}
        classes = {nome_arquivo: classe_normalizada}
    """
    refs, classes = {}, {}
    for p in sorted(dir_anot.glob("*.txt")):
        m = _PATTERN_LEI.match(p.name)
        if not m:
            continue
        texto = p.read_text(encoding="utf-8").strip()
        if not texto:
            continue
        refs[p.name]    = texto
        classes[p.name] = _normalizar_classe_lei(m.group(1))
    return refs, classes


# ──────────────────────────────────────────────────────────────────────────────
# Matching greedy (maior word_f1 primeiro)
# ──────────────────────────────────────────────────────────────────────────────

def matching_greedy(blocos, referencias, threshold):
    candidatos = []
    for b_idx, bloco in enumerate(blocos):
        texto_pred = bloco.get("texto")
        if not texto_pred:
            continue
        for ref_nome, ref_texto in referencias.items():
            m = metricas_texto(texto_pred, ref_texto)
            if m["word_f1"] >= threshold:
                candidatos.append((m["word_f1"], b_idx, ref_nome, m))

    candidatos.sort(key=lambda x: -x[0])

    usados_blocos = set()
    usados_refs   = set()
    tp_pares      = []

    for wf, b_idx, ref_nome, m in candidatos:
        if b_idx in usados_blocos or ref_nome in usados_refs:
            continue
        bloco = blocos[b_idx]
        tp_pares.append({
            "bloco_indice"  : b_idx,
            "titulo_predito": bloco.get("titulo", ""),
            "classificacao" : bloco.get("classificacao", ""),
            "pagina_inicio" : bloco.get("pagina_inicio"),
            "pagina_fim"    : bloco.get("pagina_fim"),
            "referencia"    : ref_nome,
            "metricas_texto": m,
        })
        usados_blocos.add(b_idx)
        usados_refs.add(ref_nome)

    fps = [
        {
            "bloco_indice" : i,
            "titulo"       : b.get("titulo", ""),
            "classificacao": b.get("classificacao", ""),
            "pagina_inicio": b.get("pagina_inicio"),
            "pagina_fim"   : b.get("pagina_fim"),
            "texto_extraido": bool(b.get("texto")),
        }
        for i, b in enumerate(blocos)
        if i not in usados_blocos
    ]

    fns = [r for r in referencias if r not in usados_refs]
    return tp_pares, fps, fns


# ──────────────────────────────────────────────────────────────────────────────
# Avaliação de classificação (apenas formato lei)
# ──────────────────────────────────────────────────────────────────────────────

def avaliar_classificacao(tp_pares, fps, fns, classes_ref):
    """Enriquece tp_pares com info de classificação e calcula métricas por classe.

    Para cada TP, compara classificacao predita com classe anotada.
    FP de classificação = bloco detectado mas com classe errada.
    FN de classificação = referência não detectada OU detectada com classe errada.
    """
    for par in tp_pares:
        true_cls = classes_ref.get(par["referencia"], "")
        par["classe_referencia"]    = true_cls
        par["classificacao_correta"] = (par["classificacao"] == true_cls)

    # TP_cls: detectado E classificado corretamente
    tp_cls = Counter(
        p["classe_referencia"] for p in tp_pares if p["classificacao_correta"]
    )
    # FP_cls por classe predita: detectado mas classe errada + blocos sem match
    fp_cls = Counter()
    for p in tp_pares:
        if not p["classificacao_correta"]:
            fp_cls[p["classificacao"]] += 1
    for b in fps:
        fp_cls[b["classificacao"]] += 1

    # FN_cls: referência não detectada + detectada com classe errada
    fn_cls = Counter(classes_ref[r] for r in fns if r in classes_ref)
    for p in tp_pares:
        if not p["classificacao_correta"]:
            fn_cls[p["classe_referencia"]] += 1

    todas_classes = sorted(
        set(list(tp_cls) + list(fp_cls) + list(fn_cls))
    )

    por_classe = {}
    for cls in todas_classes:
        tp = tp_cls[cls]
        fp = fp_cls[cls]
        fn = fn_cls[cls]
        p  = tp / (tp + fp) if (tp + fp) else 0.0
        r  = tp / (tp + fn) if (tp + fn) else 0.0
        f  = 2 * p * r / (p + r) if (p + r) else 0.0
        por_classe[cls] = {
            "TP": tp, "FP": fp, "FN": fn,
            "precision": round(p, 4),
            "recall"   : round(r, 4),
            "f1"       : round(f, 4),
        }

    total = len(tp_pares)
    corretos = sum(1 for p in tp_pares if p["classificacao_correta"])
    accuracy = round(corretos / total, 4) if total else 0.0

    return por_classe, accuracy, corretos, total


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Avalia detecção, extração e classificação de blocos semânticos."
    )
    parser.add_argument("--resultado",  required=True)
    parser.add_argument("--anotacoes",  required=True)
    parser.add_argument("--formato",    default="dou", choices=["dou", "lei"],
                        help="Formato das anotações: 'dou' (Pub_NN.txt) ou "
                             "'lei' ({seq}-{classe}-{pag}-{pag}.txt).")
    parser.add_argument("--threshold",  type=float, default=0.5)
    parser.add_argument("--relatorio",  default=None)
    parser.add_argument("--silencioso", action="store_true")
    args = parser.parse_args()

    with open(args.resultado, encoding="utf-8") as f:
        blocos = json.load(f)

    dir_anot = Path(args.anotacoes)

    if args.formato == "lei":
        referencias, classes_ref = carregar_referencias_lei(dir_anot)
    else:
        referencias, classes_ref = carregar_referencias_dou(dir_anot)

    if not referencias:
        print("Nenhuma referência encontrada em:", dir_anot)
        return

    print(f"\n  Formato         : {args.formato}")
    print(f"  Blocos preditos : {len(blocos)}")
    print(f"  Referências     : {len(referencias)}")
    print(f"  Threshold       : word_f1 >= {args.threshold}\n")

    tp_pares, fps, fns = matching_greedy(blocos, referencias, args.threshold)

    TP = len(tp_pares)
    FP = len(fps)
    FN = len(fns)

    precision = TP / (TP + FP) if (TP + FP) else 0.0
    recall    = TP / (TP + FN) if (TP + FN) else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    def media(campo):
        vals = [p["metricas_texto"][campo] for p in tp_pares]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    SEP = "═" * 62

    if not args.silencioso:
        print(f"{'─'*62}")
        print(f"  {'Idx':>4}  {'Referência':<30}  {'wF1':>6}  Classe predita")
        print(f"{'─'*62}")
        for par in tp_pares:
            print(
                f"  [{par['bloco_indice']:>3}]  "
                f"{par['referencia']:<30}  "
                f"{par['metricas_texto']['word_f1']:>6.3f}  "
                f"{par['classificacao']}"
            )

        if fns:
            print(f"\n  Referências não detectadas (FN = {len(fns)}):")
            for r in sorted(fns):
                print(f"    ✗ {r}")

        fp_com_texto = [b for b in fps if b["texto_extraido"]]
        if fp_com_texto:
            print(f"\n  Blocos extras sem correspondência (FP = {len(fp_com_texto)}):")
            for b in fp_com_texto:
                print(f"    ✗ [{b['bloco_indice']:>3}] {b['classificacao']}  {b['titulo'][:45]}")

    print(f"\n{SEP}")
    print(f"  Detecção de blocos  (threshold={args.threshold})")
    print(SEP)
    print(f"  TP  (detectados corretamente) : {TP}")
    print(f"  FP  (blocos sem referência)   : {FP}")
    print(f"  FN  (referências não achadas) : {FN}")
    print(f"  Precision                     : {precision:.4f}  ({precision*100:.1f}%)")
    print(f"  Recall                        : {recall:.4f}  ({recall*100:.1f}%)")
    print(f"  F1                            : {f1:.4f}  ({f1*100:.1f}%)")
    if tp_pares:
        print(f"\n  Qualidade do texto (média sobre {TP} TPs)")
        print(f"  word_f1 médio                 : {media('word_f1'):.4f}")
        print(f"  char_f1 médio                 : {media('char_f1'):.4f}")
        exatos = sum(p["metricas_texto"]["match_exato"] for p in tp_pares)
        print(f"  Matches exatos                : {exatos}/{TP}")
    print(SEP)

    # ── Classificação (apenas formato lei) ────────────────────────────────────
    por_classe = {}
    acc_info   = {}
    if args.formato == "lei" and tp_pares:
        por_classe, accuracy, corretos, total_tps = avaliar_classificacao(
            tp_pares, fps, fns, classes_ref
        )

        print(f"\n{SEP}")
        print(f"  Classificação dos blocos detectados")
        print(SEP)
        print(f"  Accuracy  : {corretos}/{total_tps}  ({accuracy*100:.1f}%)\n")
        print(f"  {'Classe':<12} {'TP':>5} {'FP':>5} {'FN':>5} {'P':>7} {'R':>7} {'F1':>7}")
        print(f"  {'─'*12} {'─'*5} {'─'*5} {'─'*5} {'─'*7} {'─'*7} {'─'*7}")
        for cls, m in sorted(por_classe.items(), key=lambda x: -x[1]["f1"]):
            print(
                f"  {cls:<12} {m['TP']:>5} {m['FP']:>5} {m['FN']:>5} "
                f"{m['precision']:>7.3f} {m['recall']:>7.3f} {m['f1']:>7.3f}"
            )
        print(SEP)

        acc_info = {"accuracy": accuracy, "corretos": corretos, "total": total_tps}

    # ── Relatório JSON ────────────────────────────────────────────────────────
    if args.relatorio:
        saida = {
            "configuracao": {
                "formato"          : args.formato,
                "threshold"        : args.threshold,
                "total_preditos"   : len(blocos),
                "total_referencias": len(referencias),
            },
            "deteccao": {
                "TP": TP, "FP": FP, "FN": FN,
                "precision": round(precision, 4),
                "recall"   : round(recall,    4),
                "f1"       : round(f1,         4),
            },
            "qualidade_texto": {
                "word_f1_media": media("word_f1"),
                "char_f1_media": media("char_f1"),
                "matches_exatos": sum(
                    p["metricas_texto"]["match_exato"] for p in tp_pares
                ),
            } if tp_pares else {},
            "classificacao"        : {"por_classe": por_classe, **acc_info},
            "verdadeiros_positivos": tp_pares,
            "falsos_positivos"     : fps,
            "falsos_negativos"     : fns,
        }
        with open(args.relatorio, "w", encoding="utf-8") as f:
            json.dump(saida, f, indent=2, ensure_ascii=False)
        print(f"\n  Relatório salvo em: {args.relatorio}")


if __name__ == "__main__":
    main()
