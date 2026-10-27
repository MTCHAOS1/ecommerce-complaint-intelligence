"""Regressões da barreira de segurança, sem conexão com PostgreSQL."""

import os
import unittest
from unittest.mock import patch

import pytest

from tests.database_safety import IsolatedDatabaseTestCase
from src.database.connection import get_engine


def test_integration_disabled_without_explicit_database(monkeypatch):
    monkeypatch.delenv("TEST_DB_NAME", raising=False)
    with pytest.raises(unittest.SkipTest, match="TEST_DB_NAME"):
        IsolatedDatabaseTestCase.setUpClass()


@pytest.mark.parametrize("database", [
    "ecommerce_complaints", "postgres", "template1", "production",
    "TEST", "app_test;DROP", "../app_test", "a" * 64 + "_test",
])
def test_unsafe_database_is_rejected(monkeypatch, database):
    monkeypatch.setenv("DB_NAME", "ecommerce_complaints")
    monkeypatch.setenv("TEST_DB_NAME", database)
    with pytest.raises(RuntimeError, match="banco da aplicação"):
        IsolatedDatabaseTestCase.setUpClass()
    assert os.environ["DB_NAME"] == "ecommerce_complaints"


def test_application_database_is_rejected_even_with_test_suffix(monkeypatch):
    monkeypatch.setenv("DB_NAME", "application_test")
    monkeypatch.setenv("TEST_DB_NAME", "application_test")
    with pytest.raises(RuntimeError, match="banco da aplicação"):
        IsolatedDatabaseTestCase.setUpClass()


def test_isolated_database_is_used_and_environment_restored(monkeypatch):
    monkeypatch.setenv("DB_NAME", "ecommerce_complaints")
    monkeypatch.setenv("TEST_DB_NAME", "ecommerce_complaints_test")

    class IntegrationCase(IsolatedDatabaseTestCase):
        pass

    try:
        IntegrationCase.setUpClass()
        assert os.environ["DB_NAME"] == "ecommerce_complaints_test"
        with patch("src.database.connection.create_engine") as create_engine:
            get_engine()
            assert create_engine.call_args.args[0].database == "ecommerce_complaints_test"
    finally:
        IntegrationCase.doClassCleanups()
    assert os.environ["DB_NAME"] == "ecommerce_complaints"


def test_environment_restored_after_class_setup_failure(monkeypatch):
    monkeypatch.setenv("DB_NAME", "ecommerce_complaints")
    monkeypatch.setenv("TEST_DB_NAME", "ecommerce_complaints_test")

    class FailingIntegrationCase(IsolatedDatabaseTestCase):
        @classmethod
        def setUpClass(cls):
            super().setUpClass()
            raise RuntimeError("Falha de preparação")

        def test_example(self):
            raise AssertionError("O teste não deve executar")

    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(FailingIntegrationCase).run(result)
    assert len(result.errors) == 1
    assert result.testsRun == 0
    assert os.environ["DB_NAME"] == "ecommerce_complaints"
