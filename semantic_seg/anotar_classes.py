#!/usr/bin/env python3
"""
anotar_classes.py — Anota Pub_NNNN.txt com categorias semânticas via LLM.

Para cada publicação, envia os primeiros ~800 caracteres ao modelo com um
prompt pedindo a classificação entre as categorias definidas no YAML.
O modelo retorna também uma confiança (alta/media/baixa) que pode ser usada
para filtrar casos a revisar manualmente com --interativo.

Resultado: arquivo classes.json em cada diretório:
  {
    "Pub_0000.txt": {
      "classe": "Atos Normativos Primários",
      "confianca": "alta",
      "motivo": "LEI Nº 15.086 — ato normativo primário do Congresso"
    },
    ...
  }

Uso:
  # Anotar um diretório
  python anotar_classes.py --dir ../scraper/pubs_extracted/dou_sec1_06-01 --config pub.yaml

  # Anotar todos os diretórios de uma raiz
  python anotar_classes.py --raiz ../scraper/pubs_extracted/ --filtro sec1 --config pub.yaml

  # Revisar interativamente os casos de baixa confiança após anotar
  python anotar_classes.py --dir ... --config pub.yaml --interativo

  # Reclassificar do zero (ignora classes.json existente)
  python anotar_classes.py --dir ... --config pub.yaml --forcar

  # Usar modelo diferente (padrão: gpt-4o-mini)
  python anotar_classes.py --dir ... --config pub.yaml --model gpt-4o
"""

import json
import sys
import time
import argparse
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Quantidade de caracteres do texto enviado ao LLM para classificação.
# 800 chars são suficientes para identificar o tipo do ato na maioria dos casos.
_CHARS_CONTEXTO = 800


# ── Prompt ────────────────────────────────────────────────────────────────────

def _construir_prompt(categorias: list[dict], texto: str) -> str:
    cats_fmt = "\n".join(
        f'{i+1}. "{c["nome"]}"\n   {c["descricao"].strip()}'
        for i, c in enumerate(categorias)
    )
    nomes = [c["nome"] for c in categorias]
    return f"""Você é um especialista em análise de documentos oficiais brasileiros (Diário Oficial da União).

## Categorias disponíveis
{cats_fmt}

## Texto da publicação (início)
{texto.strip()[:_CHARS_CONTEXTO]}

## Tarefa
Classifique esta publicação em UMA das categorias acima.

Retorne exclusivamente um JSON válido, sem texto adicional, com as chaves:
- "classe"    : string — nome exato de uma das categorias: {json.dumps(nomes, ensure_ascii=False)}
- "confianca" : string — "alta", "media" ou "baixa"
- "motivo"    : string — justificativa em uma frase curta
"""


# ── Classificação via LLM ─────────────────────────────────────────────────────

def classificar_llm(
    texto: str,
    categorias: list[dict],
    client: OpenAI,
    model: str,
    tentativas: int = 3,
) -> tuple[str | None, str, str]:
    """Retorna (classe, confianca, motivo). Em caso de falha, retorna (None, 'erro', msg)."""
    prompt = _construir_prompt(categorias, texto)
    nomes_validos = {c["nome"] for c in categorias}

    for tentativa in range(1, tentativas + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            dados = json.loads(raw)

            classe = dados.get("classe")
            confianca = dados.get("confianca", "baixa").lower()
            motivo = dados.get("motivo", "")

            if classe not in nomes_validos:
                return None, "baixa", f"classe inválida retornada: {classe!r}"
            if confianca not in ("alta", "media", "baixa"):
                confianca = "baixa"

            return classe, confianca, motivo

        except Exception as exc:
            if tentativa < tentativas:
                time.sleep(2 ** tentativa)
            else:
                return None, "erro", str(exc)

    return None, "erro", "máximo de tentativas atingido"


# ── Revisão interativa ────────────────────────────────────────────────────────

def _revisar_interativo(
    fname: str,
    texto: str,
    classe_auto: str | None,
    confianca: str,
    motivo: str,
    categorias: list[dict],
) -> tuple[str | None, str]:
    nomes = [c["nome"] for c in categorias]
    print(f"\n{'─'*64}")
    print(f"  Arquivo   : {fname}")
    print(f"  Confiança : {confianca}  |  Motivo: {motivo}")
    print(f"  Texto     : {texto[:240].strip()}")
    print(f"\n  Classificação automática: {classe_auto or '(nenhuma)'}")
    print("  Categorias:")
    for i, nome in enumerate(nomes, 1):
        print(f"    {i}. {nome}")
    print("    s. Aceitar automático   |   x. Deixar sem classe")

    while True:
        resp = input("  Escolha: ").strip().lower()
        if resp == "s":
            return classe_auto, confianca
        if resp == "x":
            return None, "desconhecida"
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(nomes):
                return nomes[idx], "manual"
        except ValueError:
            pass
        print("  Opção inválida, tente novamente.")


# ── Anotação de um diretório ──────────────────────────────────────────────────

def anotar_diretorio(
    dir_path: Path,
    config_path: Path,
    client: OpenAI,
    model: str,
    interativo: bool = False,
    threshold_revisao: str = "baixa",
    forcar: bool = False,
) -> tuple[dict, dict]:
    classes_file = dir_path / "classes.json"

    existing: dict = {}
    if classes_file.exists() and not forcar:
        with open(classes_file, encoding="utf-8") as f:
            existing = json.load(f)

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    categorias: list[dict] = cfg.get("segmentos", [])

    # Confiança igual ou abaixo do threshold dispara revisão interativa
    _ordem = {"alta": 3, "media": 2, "baixa": 1, "erro": 0}
    _limiar = _ordem.get(threshold_revisao, 1)

    resultado: dict = dict(existing)
    stats: dict[str, int] = {"alta": 0, "media": 0, "baixa": 0, "erro": 0, "existente": 0}

    pubs = sorted(dir_path.glob("Pub_*.txt"))
    for i, pub in enumerate(pubs, 1):
        fname = pub.name
        if fname in resultado and not forcar:
            stats["existente"] += 1
            continue

        texto = pub.read_text(encoding="utf-8")
        classe, confianca, motivo = classificar_llm(texto, categorias, client, model)

        print(f"  [{i:>4}/{len(pubs)}] {fname}  {confianca:<6}  {(classe or 'ERRO')[:45]}")

        if interativo and _ordem.get(confianca, 0) <= _limiar:
            classe, confianca = _revisar_interativo(
                fname, texto, classe, confianca, motivo, categorias
            )

        resultado[fname] = {"classe": classe, "confianca": confianca, "motivo": motivo}
        stats[confianca] = stats.get(confianca, 0) + 1

    with open(classes_file, "w", encoding="utf-8") as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    return stats, resultado


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anota publicações DOU com categorias semânticas via LLM."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dir",  type=Path, help="Diretório de anotações")
    group.add_argument("--raiz", type=Path, help="Raiz com múltiplos diretórios")
    parser.add_argument("--config",    type=Path, required=True,
                        help="Arquivo YAML (pub.yaml ou pub2.yaml)")
    parser.add_argument("--filtro",    default="",
                        help="Filtro de subdiretórios (ex.: sec1)")
    parser.add_argument("--model",     default="gpt-4o-mini",
                        help="Modelo OpenAI (padrão: gpt-4o-mini)")
    parser.add_argument("--interativo", action="store_true",
                        help="Revisar manualmente casos abaixo do threshold")
    parser.add_argument("--threshold-revisao", default="baixa",
                        choices=["baixa", "media", "alta"],
                        help="Nível mínimo de confiança para revisão interativa (padrão: baixa)")
    parser.add_argument("--forcar",    action="store_true",
                        help="Reclassifica mesmo arquivos já anotados")
    args = parser.parse_args()

    if not args.config.exists():
        sys.exit(f"Config não encontrada: {args.config}")

    client = OpenAI()

    dirs: list[Path] = []
    if args.dir:
        dirs = [args.dir]
    else:
        dirs = sorted(
            d for d in args.raiz.iterdir()
            if d.is_dir() and args.filtro in d.name
        )

    total: dict[str, int] = {"alta": 0, "media": 0, "baixa": 0, "erro": 0, "existente": 0}

    for d in dirs:
        pubs = list(d.glob("Pub_*.txt"))
        if not pubs:
            continue
        print(f"\n{'═'*64}")
        print(f"  {d.name}  ({len(pubs)} publicações)")
        print(f"{'─'*64}")
        stats, _ = anotar_diretorio(
            d, args.config, client, args.model,
            args.interativo, args.threshold_revisao, args.forcar,
        )
        for k, v in stats.items():
            total[k] += v
        print(
            f"\n  alta={stats['alta']}  media={stats['media']}  "
            f"baixa={stats['baixa']}  erro={stats['erro']}  "
            f"existente={stats['existente']}"
        )
        print(f"  → {d / 'classes.json'}")

    SEP = "═" * 64
    print(f"\n{SEP}")
    print(f"  Total processado: {sum(v for k,v in total.items() if k != 'existente')} novos")
    for k, v in total.items():
        print(f"  {k:<15}: {v}")
    print(SEP)


if __name__ == "__main__":
    main()
