
import unittest

from sqlalchemy import text

from src.database.connection import get_engine
from src.database.gold_lock import (
    GOLD_LOCK_ID,
    gold_execution_lock,
)


class TestGoldLock(unittest.TestCase):

    def test_lock_is_acquired_and_released(self):
        """Verifica aquisição e liberação do bloqueio."""

        engine = get_engine()

        try:
            with gold_execution_lock():
                with engine.connect() as connection:
                    acquired = connection.execute(
                        text(
                            "SELECT pg_try_advisory_lock(:lock_id)"
                        ),
                        {"lock_id": GOLD_LOCK_ID},
                    ).scalar_one()

                    connection.commit()

                    self.assertFalse(acquired)

            # Após sair do contexto, outra conexão
            # deve conseguir adquirir o bloqueio.
            with engine.connect() as connection:
                acquired = connection.execute(
                    text(
                        "SELECT pg_try_advisory_lock(:lock_id)"
                    ),
                    {"lock_id": GOLD_LOCK_ID},
                ).scalar_one()

                connection.commit()

                self.assertTrue(acquired)

                connection.execute(
                    text(
                        "SELECT pg_advisory_unlock(:lock_id)"
                    ),
                    {"lock_id": GOLD_LOCK_ID},
                )

                connection.commit()

        finally:
            engine.dispose()

    def test_second_execution_is_rejected(self):
        """Impede uma segunda operação Gold simultânea."""

        with gold_execution_lock():
            with self.assertRaisesRegex(
                RuntimeError,
                "Outra operação Gold está em andamento",
            ):
                with gold_execution_lock():
                    pass


if __name__ == "__main__":
    unittest.main()
