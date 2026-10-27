
import unittest

from sqlalchemy import text

from src.database.connection import get_engine
from tests.database_safety import PreparedDatabaseTestCase
from src.database.gold_audit import recover_interrupted_executions
from src.database.gold_lock import gold_execution_lock


class TestGoldRecovery(PreparedDatabaseTestCase):


    def test_recovery_is_blocked_during_gold_execution(self):
        """
        Impede recuperação administrativa enquanto
        outra operação mantém o Advisory Lock.
        """

        engine = get_engine()
        execution_id = None

        try:
            # Cria uma execução RUNNING antiga para o teste.
            with engine.begin() as connection:
                execution_id = connection.execute(
                    text("""
                        INSERT INTO metadata.gold_load_control
                            (periodo, status, iniciado_em)
                        VALUES (
                            DATE '2026-01-01',
                            'RUNNING',
                            CURRENT_TIMESTAMP - INTERVAL '2 hours'
                        )
                        RETURNING execution_id
                    """)
                ).scalar_one()

            # Simula uma pipeline que mantém o bloqueio.
            with gold_execution_lock():

                # A recuperação deve ser recusada.
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Outra operação Gold está em andamento",
                ):
                    recover_interrupted_executions(
                        timeout_minutes=60
                    )

                # Confirma que o registro não foi alterado.
                with engine.connect() as connection:
                    status = connection.execute(
                        text("""
                            SELECT status
                            FROM metadata.gold_load_control
                            WHERE execution_id = :execution_id
                        """),
                        {"execution_id": execution_id},
                    ).scalar_one()

                self.assertEqual(status, "RUNNING")

        finally:
            # Remove o registro temporário.
            if execution_id is not None:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            DELETE FROM metadata.gold_load_control
                            WHERE execution_id = :execution_id
                        """),
                        {"execution_id": execution_id},
                    )

            engine.dispose()


    def test_recover_interrupted_execution(self):
        engine = get_engine()
        execution_id = None

        try:
            # Criar uma execução fictícia iniciada há 2 horas.
            with engine.begin() as connection:
                execution_id = connection.execute(
                    text("""
                        INSERT INTO metadata.gold_load_control
                            (periodo, status, iniciado_em)
                        VALUES (
                            DATE '2026-01-01',
                            'RUNNING',
                            CURRENT_TIMESTAMP - INTERVAL '2 hours'
                        )
                        RETURNING execution_id
                    """)
                ).scalar_one()

            # Recuperar execuções com mais de 60 minutos.
            recovered_ids = recover_interrupted_executions(
                timeout_minutes=60
            )

            self.assertIn(execution_id, recovered_ids)

            # Verificar o resultado.
            with engine.connect() as connection:
                result = connection.execute(
                    text("""
                        SELECT
                            status,
                            finalizado_em,
                            mensagem_erro
                        FROM metadata.gold_load_control
                        WHERE execution_id = :execution_id
                    """),
                    {"execution_id": execution_id},
                ).one()

            self.assertEqual(result.status, "FAILED")
            self.assertIsNotNone(result.finalizado_em)
            self.assertIn(
                "recuperação administrativa",
                result.mensagem_erro,
            )

        finally:
            # Remover somente o registro criado pelo teste.
            if execution_id is not None:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            DELETE FROM metadata.gold_load_control
                            WHERE execution_id = :execution_id
                        """),
                        {"execution_id": execution_id},
                    )

            engine.dispose()

            
    def test_recent_execution_is_not_recovered(self):
        engine = get_engine()
        execution_id = None

        try:
            with engine.begin() as connection:
                execution_id = connection.execute(
                    text("""
                        INSERT INTO metadata.gold_load_control
                            (periodo, status, iniciado_em)
                        VALUES (
                            DATE '2026-01-01',
                            'RUNNING',
                            CURRENT_TIMESTAMP
                        )
                        RETURNING execution_id
                    """)
                ).scalar_one()

            recovered_ids = recover_interrupted_executions(
                timeout_minutes=60
            )

            self.assertNotIn(execution_id, recovered_ids)

            with engine.connect() as connection:
                status = connection.execute(
                    text("""
                        SELECT status
                        FROM metadata.gold_load_control
                        WHERE execution_id = :execution_id
                    """),
                    {"execution_id": execution_id},
                ).scalar_one()

            self.assertEqual(status, "RUNNING")

        finally:
            if execution_id is not None:
                with engine.begin() as connection:
                    connection.execute(
                        text("""
                            DELETE FROM metadata.gold_load_control
                            WHERE execution_id = :execution_id
                        """),
                        {"execution_id": execution_id},
                    )

            engine.dispose()

class TestGoldRecoveryValidation(unittest.TestCase):
    """Validações de entrada que não abrem conexão com o banco."""

    def test_invalid_timeout_is_rejected(self):
        for invalid_timeout in [0, -1, 1.5, True, "60"]:
            with self.subTest(timeout=invalid_timeout):
                with self.assertRaises(ValueError):
                    recover_interrupted_executions(
                        timeout_minutes=invalid_timeout
                    )



if __name__ == "__main__":
    unittest.main()
