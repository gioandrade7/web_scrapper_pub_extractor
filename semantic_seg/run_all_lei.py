"""
Batch runner: calls main.py for every law document in text_extraction/out/lei/
that does not yet have a corresponding output JSON in out/lei/.
Resume-safe: skips already-processed documents.
"""

import subprocess
import sys
from pathlib import Path

BASE      = Path(__file__).resolve().parent
IN_BASE   = BASE.parent / "text_extraction" / "out" / "lei"
OUT_BASE  = BASE / "out" / "lei"
MAIN      = BASE / "main.py"
CONFIG    = BASE / "lei.yaml"

MODEL          = "gpt-5.4-2026-03-05"
JANELA_PAGINAS = 10


def coletar_pendentes():
    pendentes = []
    for year_dir in sorted(p for p in IN_BASE.iterdir() if p.is_dir()):
        for law_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            txt_files = list(law_dir.glob("*.txt"))
            if not txt_files:
                continue
            out_file = OUT_BASE / year_dir.name / (law_dir.name + ".json")
            if not out_file.exists():
                pendentes.append((law_dir, out_file))
    return pendentes


def main():
    pendentes = coletar_pendentes()
    total = len(pendentes)
    if total == 0:
        print("Todos os documentos já foram processados.")
        return

    print(f"{total} documentos pendentes. Iniciando processamento...\n")

    erros = []
    for i, (law_dir, out_file) in enumerate(pendentes, 1):
        out_file.parent.mkdir(parents=True, exist_ok=True)
        label = f"{law_dir.parent.name}/{law_dir.name}"
        print(f"[{i}/{total}] {label}", flush=True)

        cmd = [
            sys.executable, str(MAIN),
            "--config",        str(CONFIG),
            "--diretorio",     str(law_dir),
            "--extensao",      ".txt",
            "--saida",         str(out_file),
            "--model",         MODEL,
            "--janela-paginas", str(JANELA_PAGINAS),
            "--so-resultado",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ERRO: {result.stderr.strip()[-300:]}", flush=True)
            erros.append(label)
        else:
            print(f"  OK → {out_file.name}", flush=True)

    print(f"\nConcluído. {total - len(erros)}/{total} processados com sucesso.")
    if erros:
        print(f"Erros ({len(erros)}):")
        for e in erros:
            print(f"  {e}")


if __name__ == "__main__":
    main()
