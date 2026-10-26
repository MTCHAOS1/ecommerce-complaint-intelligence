"""Verifica rollback de transação sem modificar o PostgreSQL real."""

import pytest
from sqlalchemy import create_engine, text


def test_staging_rollback():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE complaints (id INTEGER PRIMARY KEY)"))
            conn.execute(text("INSERT INTO complaints(id) VALUES (1)"))
        with pytest.raises(RuntimeError, match="Falha simulada"):
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM complaints"))
                raise RuntimeError("Falha simulada para testar ROLLBACK")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM complaints")).scalar_one() == 1
    finally:
        engine.dispose()
