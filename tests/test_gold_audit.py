"""Testes de integração para a auditoria da camada Gold.

Execute na raiz do projeto: python -m unittest tests.test_gold_audit -v
"""

import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy import text

from src.database.connection import get_engine
from src.database.gold_audit import (
    count_gold_records,
    fail_gold_execution,
    finish_gold_execution,
    start_gold_execution,
)


class TestGoldAudit(unittest.TestCase):
    PERIOD = "2026-07"

    @classmethod
    def setUpClass(cls):
        cls.engine = get_engine()
        with cls.engine.connect() as connection:
            cls.expected_staging = connection.execute(
                text("SELECT COUNT(*) FROM staging.complaints")
            ).scalar_one()
            cls.expected_gold = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM warehouse.fato_reclamacao f
                    JOIN warehouse.dim_tempo t ON t.data_id = f.data_id
                    WHERE t.ano = 2026 AND t.mes = 7
                """)
            ).scalar_one()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.created_ids = []

    def tearDown(self):
        if self.created_ids:
            with self.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM metadata.gold_load_control WHERE execution_id = ANY(:ids)"),
                    {"ids": self.created_ids},
                )

    def start_execution(self):
        execution_id, staging_count = start_gold_execution(self.PERIOD)
        self.created_ids.append(execution_id)
        return execution_id, staging_count

    def fetch_execution(self, execution_id):
        with self.engine.connect() as connection:
            return connection.execute(
                text("""
                    SELECT periodo, status, registros_staging, registros_gold,
                           iniciado_em, finalizado_em, mensagem_erro
                    FROM metadata.gold_load_control
                    WHERE execution_id = :id
                """),
                {"id": execution_id},
            ).mappings().one()

    def test_running_is_persisted(self):
        execution_id, staging_count = self.start_execution()
        record = self.fetch_execution(execution_id)
        self.assertEqual(record["periodo"], date(2026, 7, 1))
        self.assertEqual(record["status"], "RUNNING")
        self.assertEqual(staging_count, self.expected_staging)
        self.assertEqual(record["registros_staging"], staging_count)
        self.assertIsNone(record["registros_gold"])
        self.assertIsNotNone(record["iniciado_em"])
        self.assertIsNone(record["finalizado_em"])
        self.assertIsNone(record["mensagem_erro"])

    def test_success_is_persisted(self):
        execution_id, _ = self.start_execution()
        finish_gold_execution(execution_id, self.expected_gold)
        record = self.fetch_execution(execution_id)
        self.assertEqual(record["status"], "SUCCESS")
        self.assertEqual(record["registros_gold"], self.expected_gold)
        self.assertIsNotNone(record["finalizado_em"])
        self.assertIsNone(record["mensagem_erro"])

    def test_failed_is_persisted(self):
        execution_id, _ = self.start_execution()
        fail_gold_execution(execution_id, RuntimeError("falha simulada de teste"))
        record = self.fetch_execution(execution_id)
        self.assertEqual(record["status"], "FAILED")
        self.assertIsNone(record["registros_gold"])
        self.assertIsNotNone(record["finalizado_em"])
        self.assertIn("falha simulada de teste", record["mensagem_erro"])

    def test_cannot_finish_twice(self):
        execution_id, _ = self.start_execution()
        finish_gold_execution(execution_id, self.expected_gold)
        with self.assertRaisesRegex(RuntimeError, "não está RUNNING"):
            finish_gold_execution(execution_id, self.expected_gold)
        self.assertEqual(self.fetch_execution(execution_id)["status"], "SUCCESS")

    def test_gold_count_is_read_only(self):
        self.assertEqual(count_gold_records(self.PERIOD), self.expected_gold)


if __name__ == "__main__":
    unittest.main()
