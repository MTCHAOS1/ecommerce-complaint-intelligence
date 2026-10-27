"""Prova real da limpeza e preservação do banco usado como controle."""
import pytest

from tests import postgres_support as support


def test_control_data_survives_child_database_lifecycle(postgres):
    control, load = postgres
    control("INSERT INTO metadata.ingestion_control(period, status) VALUES ('2099-01', 'PENDING')")
    before = control('SELECT row_to_json(c)::text FROM metadata.ingestion_control c ORDER BY period')
    with support.database_on_server(control.connection_url, control.psql) as child:
        child_name = child.connection_url.database
        assert child_name != control.connection_url.database
        support.seed_audit_fixture(child)
        assert child('SELECT COUNT(*) FROM warehouse.fato_reclamacao') == '2'
    assert control('SELECT row_to_json(c)::text FROM metadata.ingestion_control c ORDER BY period') == before
    # child_name é gerado internamente por uuid4, não vem da configuração do usuário.
    assert control(f"SELECT COUNT(*) FROM pg_database WHERE datname='{child_name}'") == '0'


def test_partial_initialization_failure_removes_only_owned_database(postgres, monkeypatch):
    control, load = postgres
    before = control("SELECT datname FROM pg_database WHERE datname LIKE 'eci_%_test' ORDER BY datname")
    original = support.TestDatabase.initialize
    def failed_initialize(database):
        original(database)
        raise RuntimeError('Falha controlada depois de criar os schemas')
    monkeypatch.setattr(support.TestDatabase, 'initialize', failed_initialize)
    with pytest.raises(RuntimeError, match='Falha controlada'):
        with support.database_on_server(control.connection_url, control.psql):
            pytest.fail('Não deve executar testes após falha de preparação')
    assert control("SELECT datname FROM pg_database WHERE datname LIKE 'eci_%_test' ORDER BY datname") == before
    assert control("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema IN ('staging','warehouse','metadata')") == '8'
