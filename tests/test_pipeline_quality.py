"""Regressões da leitura Bronze até publicação Silver e preparação Staging."""
from types import SimpleNamespace
from unittest.mock import Mock
from zipfile import ZipFile

import pandas as pd
import pytest
from contextlib import contextmanager
from unittest.mock import MagicMock
from src.database import gold_lock

from src.transformation import transform_complaints as silver
from src.database import load_staging as staging
from src.ingestion.download_complaints import validate_zip
from src.ingestion.backfill import validate_local_zip


@pytest.fixture(autouse=True)
def isolated_operation_lock(monkeypatch):
    @contextmanager
    def lock():
        yield MagicMock()
    monkeypatch.setattr(gold_lock, "gold_execution_lock", lock)


def raw_frame():
    return pd.DataFrame([{
        'Região': 'Sudeste', 'UF': 'SP', 'Cidade': 'São Paulo', 'Sexo': 'F',
        'Faixa Etária': 'Adulto', 'Data Finalização': '2026-07-01',
        'Tempo Resposta': '3', 'Nome Fantasia': 'Empresa',
        'Segmento de Mercado': 'Setor', 'Área': 'Área', 'Assunto': 'Assunto',
        'Grupo Problema': 'Grupo', 'Problema': 'Problema',
        'Como Comprou Contratou': 'Internet', 'Procurou Empresa': 'S',
        'Respondida': 'N', 'Situação': 'Finalizada',
        'Avaliação Reclamação': 'Não Avaliada', 'Nota do Consumidor': None,
    }])


@pytest.mark.parametrize('column,value', [
    ('Procurou Empresa', 'INVÁLIDO'), ('Respondida', 'INVÁLIDO'),
    ('Tempo Resposta', 'abc'), ('Nota do Consumidor', 'abc'),
    ('Tempo Resposta', float('inf')), ('Nota do Consumidor', '-inf'),
])
def test_transform_rejects_lossy_conversion(column, value):
    frame = raw_frame()
    frame[column] = value
    with pytest.raises(ValueError, match='inválidos'):
        silver.transform(frame)


def test_transform_preserves_legitimate_missing_values():
    frame = raw_frame()
    columns = ['Procurou Empresa', 'Respondida', 'Tempo Resposta', 'Nota do Consumidor']
    frame[columns] = None
    result = silver.transform(frame)
    assert result[['procurou_empresa', 'respondida', 'tempo_resposta', 'nota_do_consumidor']].isna().all().all()
    from src.quality.validate_silver import validate_silver
    validate_silver(result, '2026-07')


@pytest.mark.parametrize('member', ['finalizadas_2026-07.csv', 'subpasta/finalizadas_2026-07.csv'])
def test_zip_contract_matches_ingestion_and_transformation(tmp_path, member):
    archive = tmp_path / 'bronze.zip'
    with ZipFile(archive, 'w') as zip_file:
        zip_file.writestr(member, raw_frame().to_csv(index=False, sep=';'))
    assert validate_zip(archive, '2026-07')
    assert validate_local_zip(archive, '2026-07')
    result = silver.load_raw(archive, 'finalizadas_2026-07.csv')
    assert result.loc[0, 'Nome Fantasia'] == 'Empresa'


@pytest.mark.parametrize('members', [
    [('outro.csv', 'UF\nSP\n')], [('finalizadas_2026-07.csv', '')],
    [('finalizadas_2026-07.csv', 'UF\nSP\n'), ('sub/finalizadas_2026-07.csv', 'UF\nSP\n')],
])
def test_invalid_zip_rejected_consistently(tmp_path, members):
    archive = tmp_path / 'bronze.zip'
    with ZipFile(archive, 'w') as zip_file:
        for name, content in members:
            zip_file.writestr(name, content)
    assert not validate_zip(archive, '2026-07')
    assert not validate_local_zip(archive, '2026-07')
    with pytest.raises(ValueError):
        silver.load_raw(archive, 'finalizadas_2026-07.csv')


@pytest.mark.parametrize('column,value', [('UF', 'XX'), ('Respondida', 'INVÁLIDO'), ('Tempo Resposta', 'abc')])
def test_bronze_to_silver_failure_prevents_save_and_upload(tmp_path, monkeypatch, column, value):
    archive = tmp_path / 'bronze.zip'
    frame = raw_frame()
    frame[column] = value
    with ZipFile(archive, 'w') as zip_file:
        zip_file.writestr('sub/finalizadas_2026-07.csv', frame.to_csv(index=False, sep=';'))
    monkeypatch.setattr(silver, 'get_arguments', lambda: SimpleNamespace(period='2026-07', source='local', upload_silver=True))
    monkeypatch.setattr(silver, 'get_files', lambda *args: (archive, 'finalizadas_2026-07.csv', tmp_path / 'silver.parquet'))
    save, upload = Mock(), Mock()
    monkeypatch.setattr(silver, 'save_silver', save)
    monkeypatch.setattr(silver, 'upload_silver', upload)
    with pytest.raises(ValueError):
        silver.main()
    save.assert_not_called()
    upload.assert_not_called()


def test_bronze_to_silver_success_persists_then_uploads(tmp_path, monkeypatch):
    archive, destination = tmp_path / 'bronze.zip', tmp_path / 'silver.parquet'
    with ZipFile(archive, 'w') as zip_file:
        zip_file.writestr('sub/finalizadas_2026-07.csv', raw_frame().to_csv(index=False, sep=';'))
    monkeypatch.setattr(silver, 'get_arguments', lambda: SimpleNamespace(period='2026-07', source='local', upload_silver=True))
    monkeypatch.setattr(silver, 'get_files', lambda *args: (archive, 'finalizadas_2026-07.csv', destination))
    monkeypatch.setattr(silver, 'PROCESSED_DIR', tmp_path)
    def upload(path, period):
        assert period == '2026-07'
        result = pd.read_parquet(path)
        assert bool(result.loc[0, 'procurou_empresa']) is True
        assert bool(result.loc[0, 'respondida']) is False
        assert result.loc[0, 'tempo_resposta'] == 3
    mocked_upload = Mock(side_effect=upload)
    monkeypatch.setattr(silver, 'upload_silver', mocked_upload)
    silver.main()
    mocked_upload.assert_called_once_with(destination, '2026-07')


def test_invalid_silver_never_opens_staging_connection(tmp_path, monkeypatch):
    frame = silver.transform(raw_frame())
    frame['uf'] = 'XX'
    parquet = tmp_path / 'invalid.parquet'
    frame.to_parquet(parquet, index=False)
    monkeypatch.setattr(staging, 'get_arguments', lambda: SimpleNamespace(period='2026-07', source='local'))
    monkeypatch.setattr(staging, 'get_silver_file', lambda *args: parquet)
    engine = Mock()
    monkeypatch.setattr(staging, 'get_engine', engine)
    with pytest.raises(ValueError, match='UFs inválidas'):
        staging.main()
    engine.assert_not_called()
