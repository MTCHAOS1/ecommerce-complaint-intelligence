"""Backup consistente e ensaio de restauração em destinos descartáveis.

Nunca restaura sobre o banco/buckets da aplicação. Credenciais não são gravadas.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from uuid import uuid4

import psycopg
from psycopg import sql

from src.database.connection import get_engine
from src.database.gold_lock import gold_execution_lock
from src.storage.artifacts import sha256
from src.storage.minio_client import get_minio_client

SCHEMAS = ('staging', 'warehouse', 'metadata')
BUCKETS = ('ecommerce-bronze', 'ecommerce-silver')


def command(args, *, env=None):
    result = subprocess.run([str(x) for x in args], env=env, capture_output=True,
                            text=True, timeout=1800)
    if result.returncode:
        raise RuntimeError(f'Falha de {Path(args[0]).name}; código {result.returncode}.')
    return result.stdout.strip()


def fingerprints(connection):
    """SHA-256 de todas as linhas, ordenadas pela chave primária, em streaming."""
    tables = connection.execute("""
        SELECT schemaname, tablename FROM pg_tables
        WHERE schemaname = ANY(%s) ORDER BY 1, 2
    """, (list(SCHEMAS),)).fetchall()
    result = {}
    for schema, table in tables:
        columns = connection.execute("""
            SELECT a.attname FROM pg_index i
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum, pos)
            JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum
            WHERE i.indrelid=%s::regclass AND i.indisprimary ORDER BY k.pos
        """, (f'{schema}.{table}',)).fetchall()
        query = sql.SQL('COPY (SELECT row_to_json(t)::text FROM {}.{} t ORDER BY {}) TO STDOUT').format(
            sql.Identifier(schema), sql.Identifier(table),
            sql.SQL(', ').join(sql.Identifier(c[0]) for c in columns) if columns else sql.SQL('row_to_json(t)::text COLLATE \"C\"'))
        digest, rows = hashlib.sha256(), 0
        with connection.cursor().copy(query) as stream:
            for record in stream:
                digest.update(record)
                rows += 1
        result[f'{schema}.{table}'] = {'rows': rows, 'sha256': digest.hexdigest()}
        print(f'Conferido {schema}.{table}: {rows} linhas', flush=True)
    return result


def database_config():
    engine = get_engine()
    try:
        return engine.url.translate_connect_args(username='user', database='dbname')
    finally:
        engine.dispose()


def postgres_backup(directory, config):
    environment = {**os.environ, 'PGPASSWORD': config.get('password') or ''}
    parameters = [*sum(([flag, str(config[key])] for flag, key in
                  [('-h', 'host'), ('-p', 'port'), ('-U', 'user')] if config.get(key)), [])]
    with psycopg.connect(**config) as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        snapshot = connection.execute('SELECT pg_export_snapshot()').fetchone()[0]
        expected = fingerprints(connection)
        dump = directory / 'postgres.dump'
        command(['pg_dump', *parameters, '-d', config['dbname'], '--format=custom',
                 '--no-owner', '--no-acl', '--snapshot', snapshot, '--file', dump], env=environment)
    return {'filename': dump.name, 'sha256': sha256(dump), 'tables': expected}


def minio_backup(directory, client):
    objects = directory / 'objects'
    objects.mkdir(mode=0o700)
    result = []
    for bucket in BUCKETS:
        versions = client.get_paginator('list_object_versions').paginate(Bucket=bucket)
        for page in versions:
            for version in page.get('Versions', []):
                key, version_id = version['Key'], version['VersionId']
                # Nunca usa uma chave S3 como caminho do sistema de arquivos.
                target = objects / uuid4().hex
                response = client.get_object(Bucket=bucket, Key=key, VersionId=version_id)
                try:
                    with target.open('wb') as output:
                        for block in response['Body'].iter_chunks(chunk_size=1024*1024):
                            if block:
                                output.write(block)
                finally:
                    response['Body'].close()
                result.append({'bucket': bucket, 'key': key, 'version_id': version_id,
                               'latest': version['IsLatest'], 'filename': 'objects/' + target.name,
                               'sha256': sha256(target), 'bytes': target.stat().st_size})
                print(f'Backup S3: {bucket}/{key}', flush=True)
            for marker in page.get('DeleteMarkers', []):
                result.append({'bucket': bucket, 'key': marker['Key'], 'version_id': marker['VersionId'],
                               'latest': marker['IsLatest'], 'delete_marker': True})
    return result


def backup(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat()}
    with gold_execution_lock():
        report['postgres'] = postgres_backup(directory, database_config())
        report['minio'] = minio_backup(directory, get_minio_client())
    (directory / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


@contextmanager
def temporary_postgres():
    binaries = Path(os.environ['PG_BIN']) if os.environ.get('PG_BIN') else Path(command(['pg_config', '--bindir']))
    with TemporaryDirectory(prefix='eci-recovery-', dir='/tmp') as directory:
        base = Path(directory)
        command([binaries/'initdb', '-D', base/'db', '-A', 'trust', '--no-locale', '-E', 'UTF8', '-U', 'recovery_owner'])
        try:
            command([binaries/'pg_ctl', '-D', base/'db', '-l', base/'server.log', '-w',
                     '-o', f'-k {base} -p 55440 -h ""', 'start'])
            yield {'host': str(base), 'port': 55440, 'user': 'recovery_owner', 'dbname': 'postgres'}
        finally:
            command([binaries/'pg_ctl', '-D', base/'db', '-m', 'fast', '-w', 'stop'])


def checked_file(directory, filename, digest):
    directory = Path(directory).resolve()
    path = (directory / filename).resolve()
    if not path.is_relative_to(directory) or sha256(path) != digest:
        raise ValueError('Backup ausente, fora do diretório ou com checksum divergente.')
    return path


def verify(directory):
    directory = Path(directory)
    report = json.loads((directory/'manifest.json').read_text())
    if report.get('format') != 1:
        raise ValueError('Formato de backup não suportado.')
    # Valida todo o conteúdo antes de criar qualquer destino de restauração.
    dump = checked_file(directory, report['postgres']['filename'], report['postgres']['sha256'])
    for entry in report['minio']:
        if not entry.get('delete_marker'):
            checked_file(directory, entry['filename'], entry['sha256'])
    with temporary_postgres() as config:
        command(['pg_restore', '-h', config['host'], '-p', config['port'], '-U', config['user'],
                 '-d', config['dbname'], '--no-owner', '--no-acl', '--exit-on-error', dump])
        with psycopg.connect(**config) as connection:
            actual = fingerprints(connection)
        if actual != report['postgres']['tables']:
            raise RuntimeError('Restauração PostgreSQL diverge dos hashes/contagens de origem.')
    client = get_minio_client()
    bucket = 'eci-recovery-' + uuid4().hex
    client.create_bucket(Bucket=bucket)
    restored = []
    try:
        for index, entry in enumerate(report['minio']):
            if entry.get('delete_marker'):
                continue
            key = str(index)
            path = checked_file(directory, entry['filename'], entry['sha256'])
            client.upload_file(str(path), bucket, key)
            restored.append({'Key': key})
            response = client.get_object(Bucket=bucket, Key=key)
            digest = hashlib.sha256()
            try:
                for block in response['Body'].iter_chunks(chunk_size=1024*1024):
                    digest.update(block)
            finally:
                response['Body'].close()
            if digest.hexdigest() != entry['sha256']:
                raise RuntimeError('Objeto restaurado diverge do checksum de origem.')
    finally:
        # Somente objetos e bucket aleatório criados por esta execução.
        # Lista o bucket próprio para limpar também uploads parcialmente concluídos.
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=bucket):
            keys = [{'Key': item['Key']} for item in page.get('Contents', [])]
            if keys:
                response = client.delete_objects(Bucket=bucket, Delete={'Objects': keys})
                if response.get('Errors'):
                    raise RuntimeError('Falha de limpeza do bucket descartável de recuperação.')
        client.delete_bucket(Bucket=bucket)
    result = {'verified_at': datetime.now(timezone.utc).isoformat(), 'postgres_tables': len(actual),
              'object_versions_verified': len(restored), 'status': 'SUCCESS'}
    (directory/'verification.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['backup', 'verify'])
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    try:
        result = backup(args.directory) if args.command == 'backup' else verify(args.directory)
    except Exception as error:
        parser.exit(1, f'Operação incompleta ({type(error).__name__}); nenhum destino da aplicação foi restaurado.\n')
    print(json.dumps({'status': 'SUCCESS', 'command': args.command, 'directory': str(args.directory)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
