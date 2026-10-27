"""Isolamento obrigatório para testes que acessam o PostgreSQL real."""

import os
import re
import unittest
from unittest.mock import patch


def validate_test_database_name(database, application_database):
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]{0,57}_test", database)
        or database == application_database
    ):
        raise RuntimeError(
            "TEST_DB_NAME deve terminar em _test, usar letras minúsculas, "
            "números/underscore e ser diferente de DB_NAME. "
            "Os testes não podem usar o banco da aplicação."
        )


class IsolatedDatabaseTestCase(unittest.TestCase):
    """Direciona todos os get_engine() da classe a um banco dedicado."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        database = os.environ.get("TEST_DB_NAME", "")
        if not database:
            raise unittest.SkipTest(
                "PostgreSQL de integração desabilitado: configure TEST_DB_NAME "
                "com um banco dedicado terminado em _test."
            )
        validate_test_database_name(database, os.environ.get("DB_NAME"))

        # O patch vale também para chamadas feitas pelos módulos sob teste.
        # unittest executa o cleanup mesmo quando setUpClass falha depois daqui.
        environment = patch.dict(os.environ, {"DB_NAME": database})
        environment.start()
        cls.addClassCleanup(environment.stop)


class PreparedDatabaseTestCase(IsolatedDatabaseTestCase):
    """Cada classe recebe banco novo, schemas e dados sintéticos; funciona com unittest."""

    @classmethod
    def setUpClass(cls):
        from contextlib import ExitStack
        from tests.postgres_support import postgres_database, seed_audit_fixture

        stack = ExitStack()
        cls.addClassCleanup(stack.close)
        database = stack.enter_context(postgres_database())
        configuration = database.environment
        configuration.pop('DB_NAME')  # A barreira deve comparar com o DB_NAME original.
        configuration['TEST_DB_NAME'] = database.connection_url.database
        stack.enter_context(patch.dict(os.environ, configuration))
        super().setUpClass()
        seed_audit_fixture(database)
