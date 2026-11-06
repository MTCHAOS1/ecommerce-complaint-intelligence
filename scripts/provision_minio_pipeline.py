"""Provisiona conta restrita no MinIO local; preserva credenciais existentes."""
import os
from pathlib import Path
import secrets
import shlex
import subprocess

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / '.env'
    values = dotenv_values(path)
    admin = root / '.env.minio-admin'
    if not admin.exists():
        if not all(values.get(key) for key in ('MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD')):
            raise SystemExit('Prepare .env.minio-admin com as credenciais administrativas existentes.')
        fd = os.open(admin, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as output:
            for key in ('MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD'):
                output.write(key + '=' + shlex.quote(values[key]) + '\n')
    user = values.get('MINIO_ACCESS_KEY') or 'eci-pipeline'
    password = values.get('MINIO_SECRET_KEY') or secrets.token_urlsafe(36)
    policy = (root / 'deploy/minio-pipeline-policy.json').read_text()
    script = '''set -eu
export MC_CONFIG_DIR=$(mktemp -d)
trap 'rm -rf "$MC_CONFIG_DIR"' EXIT
mc alias set audit http://127.0.0.1:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null
mc mb --ignore-existing audit/ecommerce-bronze audit/ecommerce-silver >/dev/null
mc version enable audit/ecommerce-bronze >/dev/null
mc version enable audit/ecommerce-silver >/dev/null
'''
    script += 'printf %s ' + shlex.quote(policy) + ' > "$MC_CONFIG_DIR/policy.json"\n'
    script += 'mc admin policy create audit eci-pipeline "$MC_CONFIG_DIR/policy.json" >/dev/null\n'
    script += 'mc admin user add audit ' + shlex.quote(user) + ' ' + shlex.quote(password) + ' >/dev/null\n'
    script += 'mc admin policy attach audit eci-pipeline --user ' + shlex.quote(user) + ' >/dev/null\n'
    result = subprocess.run(['docker', 'exec', '-i', 'ecommerce-minio', 'sh'],
                            input=script, text=True, capture_output=True)
    if result.returncode:
        raise SystemExit('Provisionamento falhou; saída privada não exibida. Confira o administrador no container.')
    lines = [line for line in path.read_text().splitlines() if not line.startswith((
        'MINIO_ROOT_USER=', 'MINIO_ROOT_PASSWORD=', 'MINIO_ACCESS_KEY=', 'MINIO_SECRET_KEY='))]
    lines += ['MINIO_ACCESS_KEY=' + shlex.quote(user), 'MINIO_SECRET_KEY=' + shlex.quote(password)]
    path.write_text('\n'.join(lines) + '\n')
    path.chmod(0o600)
    admin.chmod(0o600)
    print('Conta restrita provisionada; administração separada; valores não exibidos.')


if __name__ == '__main__':
    main()
