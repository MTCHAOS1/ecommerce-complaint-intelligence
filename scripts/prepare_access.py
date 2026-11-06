"""Cria login aleatório local; somente o hash é entregue ao proxy."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess

CADDY_IMAGE = 'caddy:2.11.9-alpine@sha256:0bbb055bda6793c999bde78b1b5ce3e89f829fb031af2cf50056ea1246559fee'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default='dashboard')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]{3,40}', args.username):
        parser.error('Usuário deve ter 3 a 40 letras, números, _ ou -.')
    directory = Path(__file__).resolve().parents[1] / 'deploy/secrets'
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    auth = directory / 'dashboard_auth'
    login = directory / 'dashboard_login.json'
    if auth.exists() or login.exists():
        if not (auth.is_file() and login.is_file()):
            raise SystemExit('Preparação incompleta: confira os dois arquivos privados antes de continuar.')
        print('Login existente preservado.')
        return
    password = secrets.token_urlsafe(36)
    result = subprocess.run(
        ['docker', 'run', '--rm', '-i', '--network=none', CADDY_IMAGE,
         'caddy', 'hash-password', '--algorithm', 'argon2id'],
        input=password, text=True, capture_output=True, check=True)
    hashed = result.stdout.strip()
    if not hashed.startswith('$argon2id$') or '\n' in hashed:
        raise RuntimeError('Resposta de hash inválida.')
    for path, content, mode in [
        (login, json.dumps({'username': args.username, 'password': password}), 0o600),
        (auth, f'{args.username} {hashed}\n', 0o444),
    ]:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, 'w') as output:
            output.write(content)
    print('Login preparado. Credencial em deploy/secrets/dashboard_login.json; valores não exibidos.')


if __name__ == '__main__':
    main()
