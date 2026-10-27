"""As cópias compatíveis devem preservar o CSV e o arquivo original."""

import shutil
import subprocess
from zipfile import ZipFile

import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock
from src.database import gold_lock

from scripts import prepare_bronze_zip as normalizer


@pytest.fixture(autouse=True)
def isolated_operation_lock(monkeypatch):
    @contextmanager
    def lock():
        yield MagicMock()
    monkeypatch.setattr(gold_lock, "gold_execution_lock", lock)


@pytest.mark.skipif(shutil.which("7z") is None, reason="Requer 7z instalado")
@pytest.mark.parametrize("nested", [False, True])
def test_normalization_preserves_source_and_csv(tmp_path, monkeypatch, nested):
    monkeypatch.setattr(normalizer, "ROOT", tmp_path)
    csv_file = tmp_path / "finalizadas_2026-05.csv"
    csv_data = "Data Finalização;UF\n2026-05-01;SP\n".encode()
    csv_file.write_bytes(csv_data)
    member = csv_file
    if nested:
        member = tmp_path / "finalizadas_2026-05.7z"
        subprocess.run(["7z", "a", str(member), str(csv_file)], check=True, capture_output=True)
    source = tmp_path / "original.zip"
    with ZipFile(source, "w") as archive:
        archive.write(member, arcname=member.name)
    original_hash = normalizer.sha256(source)

    normalizer.prepare("2026-05", source)

    assert normalizer.sha256(source) == original_hash
    destination = tmp_path / "data/raw/finalizadas_2026-05.zip"
    with ZipFile(destination) as archive:
        assert archive.read(csv_file.name) == csv_data
    with pytest.raises(FileExistsError):
        normalizer.prepare("2026-05", source)
