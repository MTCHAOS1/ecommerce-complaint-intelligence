"""Fixtures PostgreSQL compartilhadas; o opt-in fica no suporte, antes de conectar."""
import pytest

from tests.postgres_support import postgres_database


@pytest.fixture(scope='module')
def postgres():
    with postgres_database() as database:
        yield database, database.load
