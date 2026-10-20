
"""Controle de concorrência da camada Gold."""

from contextlib import contextmanager

from sqlalchemy import text

from src.database.connection import get_engine


# Identificador exclusivo do bloqueio da pipeline.
GOLD_LOCK_ID = 20261020


@contextmanager
def gold_execution_lock():
    """
    Mantém um Advisory Lock durante toda a operação.

    O bloqueio é liberado ao sair do contexto,
    inclusive quando ocorre uma exceção.
    """

    engine = get_engine()

    try:
        with engine.connect() as connection:
            acquired = connection.execute(
                text(
                    "SELECT pg_try_advisory_lock(:lock_id)"
                ),
                {"lock_id": GOLD_LOCK_ID},
            ).scalar_one()

            # Encerra a transação implícita do SELECT,
            # mantendo o lock de sessão.
            connection.commit()

            if not acquired:
                raise RuntimeError(
                    "Outra operação Gold está em andamento."
                )

            try:
                yield

            finally:
                released = connection.execute(
                    text(
                        "SELECT pg_advisory_unlock(:lock_id)"
                    ),
                    {"lock_id": GOLD_LOCK_ID},
                ).scalar_one()

                connection.commit()

                if not released:
                    raise RuntimeError(
                        "Não foi possível liberar o bloqueio Gold."
                    )

    finally:
        engine.dispose()
