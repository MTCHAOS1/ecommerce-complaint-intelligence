
"""Controle de concorrência da camada Gold."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import os
import threading

from sqlalchemy import text

from src.database.connection import get_engine


# Identificador exclusivo do bloqueio da pipeline.
GOLD_LOCK_ID = 20261020

# Nunca é transmitido por argumento CLI ou variável de ambiente.
_ACTIVE_OPERATION = ContextVar("pipeline_operation", default=None)


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

            token = _ACTIVE_OPERATION.set((os.getpid(), threading.get_ident(), connection))
            try:
                yield connection

            finally:
                _ACTIVE_OPERATION.reset(token)
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


@contextmanager
def pipeline_operation():
    """Reutiliza o lock somente no mesmo processo/thread e contexto de chamada."""
    active = _ACTIVE_OPERATION.get()
    if active is not None and active[:2] == (os.getpid(), threading.get_ident()):
        yield active[2]
    else:
        with gold_execution_lock() as connection:
            yield connection


def exclusive_operation(function):
    """Protege uma operação pública, incluindo chamadas feitas fora da CLI."""
    @wraps(function)
    def protected(*args, **kwargs):
        with pipeline_operation():
            return function(*args, **kwargs)
    return protected
