"""Prepara ZIP compatível com a pipeline, preservando o arquivo de origem.

Requer 7z no PATH. Aceita CSV direto ou 7z aninhado no arquivo mensal.
"""

import argparse
import sys
import hashlib
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database.gold_lock import exclusive_operation


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def extract_member(archive, member, destination):
    subprocess.run(["7z", "t", str(archive)], check=True, capture_output=True)
    with destination.open("wb") as output:
        subprocess.run(
            ["7z", "x", "-so", str(archive), member],
            stdout=output, stderr=subprocess.PIPE, check=True,
        )
    if destination.stat().st_size == 0:
        raise ValueError(f"Arquivo ausente ou vazio: {member}")


@exclusive_operation
def prepare(period, source):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
        raise ValueError("Período inválido: use YYYY-MM.")
    csv_name = f"finalizadas_{period}.csv"
    nested_name = f"finalizadas_{period}.7z"
    destination = ROOT / "data" / "raw" / f"finalizadas_{period}.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"Destino já existe; preservado: {destination}")
    with TemporaryDirectory(prefix="prepare-bronze-") as temporary:
        temporary = Path(temporary)
        with ZipFile(source) as archive:
            names = archive.namelist()
        csv_file = temporary / csv_name
        if csv_name in names:
            extract_member(source, csv_name, csv_file)
        elif nested_name in names:
            nested = temporary / nested_name
            extract_member(source, nested_name, nested)
            extract_member(nested, csv_name, csv_file)
        else:
            raise ValueError(f"CSV/7z esperado não encontrado: {names}")
        # Exclusão automática do temporário em caso de falha.
        with TemporaryDirectory(dir=destination.parent, prefix="normalize-") as output_dir:
            output_zip = Path(output_dir) / destination.name
            with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as archive:
                archive.write(csv_file, arcname=csv_name)
            with ZipFile(output_zip) as archive:
                if archive.testzip() is not None:
                    raise ValueError("ZIP normalizado corrompido.")
            output_zip.replace(destination)
        print(f"Origem preservada: {source}")
        print(f"SHA256 origem: {sha256(source)}")
        print(f"SHA256 CSV: {sha256(csv_file)}")
        print(f"ZIP normalizado: {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("period")
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    prepare(args.period, args.source.resolve())


if __name__ == "__main__":
    main()
