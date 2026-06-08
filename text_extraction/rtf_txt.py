import os
import subprocess
from pathlib import Path

from striprtf.striprtf import rtf_to_text
# Example RTF string

def convert_rtf_file_to_text(file_path):
    # Open and read the RTF file content
    with open(file_path, "r", encoding="cp1252") as f:
        rtf_content = f.read()
    
    # Convert the RTF string to plain text
    plain_text = rtf_to_text(rtf_content)
    return plain_text


base_rtf = Path('./data/rtf')

for ano_dir in sorted(base_rtf.iterdir()):
    if not ano_dir.is_dir():
        continue

    ano = ano_dir.name
    rtf_docs = sorted(ano_dir.iterdir())

    out_path = Path(f'out/lei/lei_{ano}')
    out_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for input_path in rtf_docs:
        if input_path.suffix.lower() != '.rtf':
            continue

        doc_dir = out_path / f"lei_{count:04d}"
        doc_dir.mkdir(exist_ok=True)
        output_path = doc_dir / f"lei_{count:04d}.txt"

        text = convert_rtf_file_to_text(input_path)

        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(text)

        print(f"✓ [{ano}] {input_path.name}")
        count += 1

    print(f"── {ano}: {count} lei(s) processada(s)")
