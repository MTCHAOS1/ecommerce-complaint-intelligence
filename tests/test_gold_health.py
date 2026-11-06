"""Cobertura real da Gold, inconsistências de auditoria e contratos da CLI."""

from datetime import date, datetime, timezone
import json
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine

from src.monitoring import gold_health
from tests.postgres_support import seed_audit_fixture


@pytest.fixture
def health_database(postgres, monkeypatch):
    database, _ = postgres
    database('TRUNCATE metadata.gold_load_control, staging.complaints, '
             'warehouse.fato_reclamacao, warehouse.dim_empresa, '
             'warehouse.dim_localidade, warehouse.dim_tempo, '
             'warehouse.dim_classificacao RESTART IDENTITY')
    seed_audit_fixture(database)
    database("""
        INSERT INTO metadata.gold_load_control
            (periodo, status, registros_staging, registros_gold, finalizado_em)
        VALUES ('2026-07-01', 'SUCCESS', 2, 2, NOW());
    """)
    monkeypatch.setattr(gold_health, 'get_engine', lambda: create_engine(database.connection_url))
    return database


def test_coverage_keeps_missing_months_and_reports_latest_success(health_database):
    report = gold_health.get_gold_health('2026-06', '2026-08')
    assert [row['registros_gold'] for row in report['periodos']] == [0, 2, 0]
    assert report['meses_sem_dados'] == [date(2026, 6, 1), date(2026, 8, 1)]
    assert report['ultimo_periodo_com_dados'] == date(2026, 7, 1)
    assert report['ultima_carga_sucesso'] is not None
    assert report['total_reclamacoes'] == 2
    assert not any(a['periodo'] == date(2026, 7, 1) for a in report['alertas'])
    assert {a['codigo'] for a in report['alertas']} == {'SEM_DADOS', 'SEM_AUDITORIA'}


def test_latest_failure_does_not_hide_existing_facts_or_previous_success(health_database):
    health_database("""
        INSERT INTO metadata.gold_load_control (periodo, status)
        VALUES ('2026-07-01', 'FAILED');
    """)
    report = gold_health.get_gold_health('2026-07', '2026-07')
    assert report['total_reclamacoes'] == 2
    assert report['ultima_carga_sucesso'] is not None
    assert report['alertas'] == [{'periodo': date(2026, 7, 1), 'codigo': 'ULTIMA_CARGA_FALHOU'}]


def test_audited_count_mismatch_is_reported(health_database):
    health_database('UPDATE metadata.gold_load_control SET registros_gold = 3')
    report = gold_health.get_gold_health('2026-07', '2026-07')
    assert [a['codigo'] for a in report['alertas']] == ['CONTAGEM_DIVERGENTE']


def test_long_running_includes_older_attempts_without_modifying_status(health_database):
    health_database("""
        INSERT INTO metadata.gold_load_control (periodo, status, iniciado_em)
        VALUES ('2026-07-01', 'RUNNING', NOW() - INTERVAL '2 hours'),
               ('2026-07-01', 'RUNNING', NOW()),
               ('2026-08-01', 'RUNNING', NOW() - INTERVAL '2 hours');
        INSERT INTO metadata.gold_load_control
            (periodo, status, registros_staging, registros_gold, finalizado_em)
        VALUES ('2026-07-01', 'SUCCESS', 2, 2, NOW());
    """)
    report = gold_health.get_gold_health('2026-07', '2026-07', 60)
    assert len(report['execucoes_prolongadas']) == 1
    assert report['execucoes_prolongadas'][0]['duracao_segundos'] >= 7200
    assert [a['codigo'] for a in report['alertas']] == ['EXECUCAO_PROLONGADA']
    assert health_database("SELECT COUNT(*) FROM metadata.gold_load_control WHERE status='RUNNING'") == '3'


def test_empty_warehouse_has_no_fabricated_last_update(health_database):
    report = gold_health.get_gold_health('2026-08', '2026-08')
    assert report['total_reclamacoes'] == 0
    assert report['ultimo_periodo_com_dados'] is None
    assert report['ultima_carga_sucesso'] is None


def test_facts_without_audit_are_not_reported_as_missing_data(health_database):
    health_database('TRUNCATE metadata.gold_load_control')
    report = gold_health.get_gold_health('2026-07', '2026-07')
    assert report['total_reclamacoes'] == 2
    assert report['meses_sem_dados'] == []
    assert [alert['codigo'] for alert in report['alertas']] == ['SEM_AUDITORIA']


def test_diagnostic_transaction_rejects_writes(health_database, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    monkeypatch.setattr(gold_health, 'COVERAGE_SQL', text('DELETE FROM staging.complaints'))
    with pytest.raises(DBAPIError) as error:
        gold_health.get_gold_health('2026-07', '2026-07')
    assert error.value.orig.sqlstate == '25006'
    assert health_database('SELECT COUNT(*) FROM staging.complaints') == '2'


@pytest.mark.parametrize('start,end,timeout', [
    ('bad', '2026-07', 60), ('2026-08', '2026-07', 60),
    ('2026-07', '2026-07', 0), ('2026-07', '2026-07', True),
])
def test_invalid_input_never_connects(monkeypatch, start, end, timeout):
    engine = Mock(side_effect=AssertionError('não deve conectar'))
    monkeypatch.setattr(gold_health, 'get_engine', engine)
    with pytest.raises(ValueError):
        gold_health.get_gold_health(start, end, timeout)
    engine.assert_not_called()


def test_json_check_is_machine_readable_and_returns_one_on_alert(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['gold_health', '--start', '2026-07', '--end', '2026-07', '--json', '--check'])
    monkeypatch.setattr(gold_health, 'get_gold_health', Mock(return_value={
        'verificado_em': datetime(2026, 11, 4, tzinfo=timezone.utc),
        'alertas': [{'periodo': date(2026, 7, 1), 'codigo': 'SEM_DADOS'}],
    }))
    with pytest.raises(SystemExit) as result:
        gold_health.main()
    assert result.value.code == 1
    data = json.loads(capsys.readouterr().out)
    assert data['alertas'][0]['periodo'] == '2026-07-01'


def test_cli_connection_error_hides_credentials(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['gold_health', '--start', '2026-07', '--end', '2026-07', '--json'])
    monkeypatch.setattr(gold_health, 'get_gold_health', Mock(side_effect=RuntimeError('private-password')))
    with pytest.raises(SystemExit) as result:
        gold_health.main()
    assert result.value.code == 2
    output = capsys.readouterr()
    assert not output.out
    assert 'private-password' not in output.err


def test_cli_success_returns_zero(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['gold_health', '--start', '2026-07', '--end', '2026-07', '--json', '--check'])
    monkeypatch.setattr(gold_health, 'get_gold_health', Mock(return_value={'alertas': []}))
    gold_health.main()
    assert json.loads(capsys.readouterr().out) == {'alertas': []}


def test_invalid_historical_domain_is_reported_without_rewriting(health_database):
    health_database('UPDATE warehouse.fato_reclamacao SET tempo_resposta=-4 WHERE data_id=20260701')
    report = gold_health.get_gold_health('2026-07', '2026-07')
    assert report['periodos'][0]['registros_invalidos'] == 1
    assert [a['codigo'] for a in report['alertas']] == ['DOMINIO_INVALIDO']
    assert health_database('SELECT tempo_resposta FROM warehouse.fato_reclamacao WHERE data_id=20260701') == '-4'
