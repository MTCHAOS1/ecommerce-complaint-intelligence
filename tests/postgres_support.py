"""PostgreSQL descartável para pytest e unittest, sem reutilizar dados existentes."""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql as pg_sql
from sqlalchemy.engine import URL

from tests.database_safety import validate_test_database_name


ROOT = Path(__file__).resolve().parents[1]


def run_command(arguments, *, env=None):
    return subprocess.run([str(argument) for argument in arguments], text=True,
                          capture_output=True, timeout=30, env=env)


def require_success(result):
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Falha de preparação PostgreSQL.')
    return result.stdout.strip()


@dataclass
class TestDatabase:
    __test__ = False
    connection_url: URL
    psql: str

    @property
    def environment(self):
        return {
            'DB_HOST': self.connection_url.host or '',
            'DB_PORT': str(self.connection_url.port or 5432),
            'DB_USER': self.connection_url.username or '',
            'DB_PASSWORD': self.connection_url.password or '',
            'DB_NAME': self.connection_url.database,
        }

    @property
    def psql_prefix(self):
        env = self.environment
        return [self.psql, '-X', '-w', '-h', env['DB_HOST'], '-p', env['DB_PORT'],
                '-U', env['DB_USER'], '-d', env['DB_NAME'], '-v', 'ON_ERROR_STOP=1']

    def run(self, arguments):
        # Credenciais não entram nos argumentos nem no relatório de testes.
        return run_command(arguments, env={**os.environ,
                           'PGPASSWORD': self.connection_url.password or '', 'PGCONNECT_TIMEOUT': '10'})

    def __call__(self, statement):
        return require_success(self.run(self.psql_prefix + ['-Atc', statement]))

    def load(self, period='2026-07'):
        parameters = [] if period is None else ['-v', f'expected_period={period}']
        return self.run(self.psql_prefix + parameters + ['-f', ROOT / 'sql/warehouse/load_star_schema.sql'])

    def initialize(self):
        require_success(self.run(self.psql_prefix + ['-f', ROOT / 'sql/init_database.sql']))


def find_binaries():
    configured = os.environ.get('PG_BIN')
    if configured:
        directory = Path(configured)
    else:
        pg_config = shutil.which('pg_config')
        if not pg_config:
            raise RuntimeError('Configure PG_BIN ou instale pg_config e os binários PostgreSQL 15+.')
        directory = Path(require_success(run_command([pg_config, '--bindir'])))
    for name in ('initdb', 'pg_ctl', 'psql'):
        if not (directory / name).is_file():
            raise RuntimeError(f'Binário PostgreSQL ausente: {directory / name}')
    return directory


@contextmanager
def local_postgres_server():
    """Cluster sem TCP em diretório/socket exclusivos; não consulta DB_* ou TEST_DB_NAME."""
    binaries = find_binaries()
    with tempfile.TemporaryDirectory(prefix='eci-pg-', dir='/tmp') as directory:
        base = Path(directory)
        require_success(run_command([binaries / 'initdb', '-D', base / 'db', '-A', 'trust',
                                     '--no-locale', '-E', 'UTF8', '-U', 'eci_test_owner']))
        try:
            result = run_command([binaries / 'pg_ctl', '-D', base / 'db', '-l', base / 'log',
                                  '-o', f'-k {base} -p 55439 -h ""', '-w', 'start'])
            if result.returncode:
                raise RuntimeError((base / 'log').read_text())
            yield URL.create('postgresql+psycopg', username='eci_test_owner',
                             host=str(base), port=55439, database='postgres'), str(binaries / 'psql')
        finally:
            result = run_command([binaries / 'pg_ctl', '-D', base / 'db', '-m', 'fast', '-w', 'stop'])
            if result.returncode and (base / 'db/postmaster.pid').exists():
                require_success(result)


@contextmanager
def database_on_server(admin_url, psql):
    """Cria e remove SOMENTE o nome aleatório criado por esta execução."""
    name = f'eci_{uuid4().hex}_test'
    connection_arguments = admin_url.translate_connect_args(username='user', database='dbname')
    with psycopg.connect(**connection_arguments, autocommit=True, connect_timeout=10) as admin:
        try:
            admin.execute(pg_sql.SQL('CREATE DATABASE {}').format(pg_sql.Identifier(name)))
        except psycopg.errors.InsufficientPrivilege as error:
            raise RuntimeError('O usuário de integração precisa de CREATEDB; ou use RUN_TEMP_POSTGRES_TESTS=1.') from error
        # Só entra no finally após CREATE bem-sucedido: não remove banco preexistente.
        try:
            url = URL.create('postgresql+psycopg', username=admin.info.user,
                             password=admin_url.password, host=admin.info.host,
                             port=admin.info.port, database=name)
            database = TestDatabase(url, psql)
            database.initialize()
            yield database
        finally:
            admin.execute(pg_sql.SQL('DROP DATABASE {} WITH (FORCE)').format(pg_sql.Identifier(name)))


@contextmanager
def postgres_database():
    """Opt-in local ou servidor de testes explícito; desabilitado não abre conexão."""
    if os.environ.get('RUN_TEMP_POSTGRES_TESTS') == '1':
        with local_postgres_server() as (url, psql):
            with database_on_server(url, psql) as database:
                yield database
        return
    database = os.environ.get('TEST_DB_NAME', '')
    if not database:
        raise unittest.SkipTest('Configure RUN_TEMP_POSTGRES_TESTS=1 ou TEST_DB_NAME dedicado terminado em _test.')
    validate_test_database_name(database, os.environ.get('DB_NAME'))
    psql = shutil.which('psql')
    if not psql:
        raise RuntimeError('Instale o cliente psql para usar o servidor PostgreSQL de testes.')
    url = URL.create('postgresql+psycopg', username=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD'),
                     host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT', '5432')), database=database)
    with database_on_server(url, psql) as prepared:
        yield prepared


def seed_audit_fixture(database):
    """Julho sintético: duas linhas na Staging e duas na Gold, sem downloads."""
    database("""
        INSERT INTO staging.complaints
            (data_finalizacao, nome_fantasia, uf, cidade, avaliacao_reclamacao, nota_do_consumidor)
        VALUES ('2026-07-01', 'Empresa sintética', 'SP', 'São Paulo', 'Resolvida', 3),
               ('2026-07-02', 'Empresa sintética', 'SP', 'São Paulo', 'Não Avaliada', NULL);
    """)
    require_success(database.load())
