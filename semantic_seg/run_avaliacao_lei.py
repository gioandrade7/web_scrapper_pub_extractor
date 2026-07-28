"""
Batch evaluation: runs avaliar.py --formato lei for every law document that
already has a segmentation result JSON in out/lei/.

Mapping lei_NNNN -> LEI-{year}-{number}: the N-th (0-indexed) document in
out/lei/lei_{year}/ corresponds to the N-th directory (sorted) in
dataset3txtLEI/{year}/ -- verified 1:1 for all processed years/docs.

Resume-safe: skips documents whose relatorio JSON already exists.
"""

import subprocess
import sys
from pathlib import Path

BASE      = Path(__file__).resolve().parent
OUT_BASE  = BASE / "out" / "lei"
REL_BASE  = OUT_BASE / "relatorios"
ANOT_BASE = Path("/Users/gioandrade/Documents/mestrado/datasets/dataset_lei/dataset3txtLEI")
AVALIAR   = BASE / "avaliar.py"

THRESHOLD = 0.5


def coletar_pendentes():
    pendentes = []
    for ano_dir in sorted(p for p in OUT_BASE.iterdir() if p.is_dir() and p.name.startswith("lei_")):
        year = ano_dir.name.replace("lei_", "")
        anot_year_dir = ANOT_BASE / year
        if not anot_year_dir.is_dir():
            continue
        sorted_dirs = sorted(p.name for p in anot_year_dir.iterdir() if p.is_dir())

        for out_json in sorted(ano_dir.glob("lei_*.json")):
            doc = out_json.stem
            idx = int(doc.replace("lei_", ""))
            if idx >= len(sorted_dirs):
                continue
            anot_dir = anot_year_dir / sorted_dirs[idx]
            rel_file = REL_BASE / f"{ano_dir.name}_{doc}_relatorio.json"
            if not rel_file.exists():
                pendentes.append((ano_dir.name, doc, out_json, anot_dir, rel_file))
    return pendentes


def main():
    pendentes = coletar_pendentes()
    total = len(pendentes)
    if total == 0:
        print("Todos os documentos já foram avaliados.")
        return

    REL_BASE.mkdir(parents=True, exist_ok=True)
    print(f"{total} documentos pendentes. Iniciando avaliação...\n")

    erros = []
    for i, (ano, doc, out_json, anot_dir, rel_file) in enumerate(pendentes, 1):
        label = f"{ano}/{doc}"
        cmd = [
            sys.executable, str(AVALIAR),
            "--resultado",  str(out_json),
            "--anotacoes",  str(anot_dir),
            "--formato",    "lei",
            "--threshold",  str(THRESHOLD),
            "--relatorio",  str(rel_file),
            "--silencioso",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[{i}/{total}] {label}  ERRO: {result.stderr.strip()[-300:]}", flush=True)
            erros.append(label)
        else:
            print(f"[{i}/{total}] {label}  OK", flush=True)

    print(f"\nConcluído. {total - len(erros)}/{total} avaliados com sucesso.")
    if erros:
        print(f"Erros ({len(erros)}):")
        for e in erros:
            print(f"  {e}")


if __name__ == "__main__":
    main()
