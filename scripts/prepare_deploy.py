"""Gera segredos locais para o ambiente isolado, sem substituir arquivos existentes."""
from pathlib import Path
import os
import secrets


def main():
    directory = Path(__file__).resolve().parents[1]/'deploy/secrets'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    for name in ('postgres_password', 'pipeline_password', 'reader_password'):
        path = directory/name
        try:
            descriptor = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o444)
        except FileExistsError:
            os.chmod(path, 0o444)
            continue
        with os.fdopen(descriptor, 'w') as output:
            output.write(secrets.token_urlsafe(36))
    print('Segredos locais preparados; valores não exibidos.')


if __name__ == '__main__':
    main()
