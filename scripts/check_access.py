"""Ensaio local de HTTPS, autenticação e WebSocket; não imprime credenciais."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request


def main():
    os.environ['DASHBOARD_DOMAIN'] = 'localhost'
    compose = ['docker', 'compose', '-f', 'deploy/compose.yml', '-f', 'deploy/compose.access.yml']
    for attempt in range(30):
        result = subprocess.run(compose + ['exec', '-T', 'proxy', 'cat',
            '/data/caddy/pki/authorities/local/root.crt'], capture_output=True, text=True)
        if result.returncode == 0:
            break
        if attempt == 29:
            raise RuntimeError('CA local do proxy indisponível.')
        time.sleep(1)
    context = ssl.create_default_context(cadata=result.stdout)
    login = json.loads(Path('deploy/secrets/dashboard_login.json').read_text())
    auth = 'Basic ' + base64.b64encode((login['username'] + ':' + login['password']).encode()).decode()

    def request(path, authorization=None):
        headers = {'Authorization': authorization} if authorization else {}
        try:
            with urllib.request.urlopen(urllib.request.Request('https://localhost:8443' + path,
                    headers=headers), context=context, timeout=10) as response:
                return response.status, response.headers
        except urllib.error.HTTPError as error:
            return error.code, error.headers

    for attempt in range(30):
        try:
            assert request('/')[0] == 401
            break
        except (OSError, AssertionError):
            if attempt == 29:
                raise
            time.sleep(1)
    for path in ['/', '/_stcore/health', '/_stcore/stream', '/favicon.png']:
        assert request(path)[0] == 401, path
    wrong = 'Basic ' + base64.b64encode(b'invalid:invalid').decode()
    assert request('/', wrong)[0] == 401
    status, headers = request('/', auth)
    assert status == 200
    assert headers['X-Content-Type-Options'] == 'nosniff'
    assert 'max-age=' in headers['Strict-Transport-Security']
    assert request('/_stcore/health', auth)[0] == 200
    with context.wrap_socket(socket.create_connection(('localhost', 8443), timeout=10),
                             server_hostname='localhost') as connection:
        upgrade = ('GET /_stcore/stream HTTP/1.1\r\nHost: localhost:8443\r\n'
            'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\n'
            'Sec-WebSocket-Key: ' + base64.b64encode(secrets.token_bytes(16)).decode() + '\r\n'
            'Sec-WebSocket-Protocol: streamlit\r\nOrigin: https://localhost:8443\r\n'
            'Authorization: ' + auth + '\r\n\r\n')
        connection.sendall(upgrade.encode())
        assert b' 101 ' in connection.recv(4096).split(b'\r\n', 1)[0]
    container = subprocess.check_output(compose + ['ps', '-q', 'dashboard'], text=True).strip()
    bindings = subprocess.check_output(['docker', 'inspect', container,
        '--format', '{{json .HostConfig.PortBindings}}'], text=True)
    assert not json.loads(bindings), 'Porta direta do dashboard foi publicada.'
    print('HTTPS com CA validada; login ausente/incorreto bloqueado; login válido e WebSocket aprovados; sem porta direta.')


if __name__ == '__main__':
    main()
