#!/usr/bin/env python3
"""
run_all_dou.py — Batch runner: roda main.py para cada documento do DOU em
text_extraction/out/dou/ que ainda não tem JSON de blocos em out/dou/blocos/.

Resume-safe: pula documentos já processados (a menos de --forcar).

Uso:
  python run_all_dou.py --filtro sec1 --config pub.yaml --model gpt-5.4-2026-03-05
  python run_all_dou.py --filtro sec1 --dry-run     # apenas lista o que rodaria
  python run_all_dou.py --filtro sec2 --config pub2.yaml --forcar
"""

import sys
import time
import argparse
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / ".." / "text_extraction" / "out" / "dou"
SAIDA = BASE / "out" / "dou" / "blocos"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch runner de segmentação do DOU.")
    parser.add_argument("--filtro",  default="sec1", help="Filtro de subdiretórios (ex.: sec1).")
    parser.add_argument("--config",  default="pub.yaml", help="Config YAML/JSON.")
    parser.add_argument("--model",   default="gpt-5.4-2026-03-05", help="Modelo OpenAI.")
    parser.add_argument("--janela-paginas", default=10, type=int)
    parser.add_argument("--forcar",  action="store_true", help="Reprocessa mesmo já existentes.")
    parser.add_argument("--dry-run", action="store_true", help="Só lista o que rodaria.")
    args = parser.parse_args()

    SAIDA.mkdir(parents=True, exist_ok=True)

    dirs = sorted(
        d for d in ENTRADA.iterdir()
        if d.is_dir() and args.filtro in d.name
    )
    if not dirs:
        sys.exit(f"Nenhum diretório com filtro {args.filtro!r} em {ENTRADA}")

    pendentes = []
    for d in dirs:
        saida_json = SAIDA / f"{d.name}.json"
        if saida_json.exists() and not args.forcar:
            print(f"  [skip] {d.name}  (já existe {saida_json.name})")
            continue
        pendentes.append((d, saida_json))

    print(f"\n  Total: {len(dirs)} dirs  |  a processar: {len(pendentes)}  |  modelo: {args.model}\n")

    if args.dry_run:
        for d, _ in pendentes:
            n = len(list(d.glob("*.md")))
            print(f"    would run: {d.name}  ({n} páginas)")
        return

    ok, falhas = 0, []
    for i, (d, saida_json) in enumerate(pendentes, 1):
        n = len(list(d.glob("*.md")))
        print(f"\n{'='*64}\n  [{i}/{len(pendentes)}] {d.name}  ({n} páginas)\n{'='*64}")
        t0 = time.time()
        cmd = [
            sys.executable, str(BASE / "main.py"),
            "--config", args.config,
            "--diretorio", str(d),
            "--saida", str(saida_json),
            "--model", args.model,
            "--janela-paginas", str(args.janela_paginas),
            "--so-resultado",
        ]
        res = subprocess.run(cmd, cwd=str(BASE))
        dt = time.time() - t0
        if res.returncode == 0 and saida_json.exists():
            ok += 1
            print(f"  OK  {d.name}  ({dt:.0f}s)")
        else:
            falhas.append(d.name)
            print(f"  FALHA  {d.name}  (returncode={res.returncode}, {dt:.0f}s)")

    print(f"\n{'='*64}")
    print(f"  Concluído: {ok}/{len(pendentes)} com sucesso.")
    if falhas:
        print(f"  Falhas ({len(falhas)}): {', '.join(falhas)}")
    print(f"{'='*64}")


if __name__ == "__main__":
    main()
