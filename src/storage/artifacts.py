"""Hashes, manifestos e publicação versionada sem credenciais nos metadados."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import os
import tempfile


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def manifest_path(path):
    return Path(str(path) + '.lineage.json')


def atomic_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix='.lineage-')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(payload, output, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_manifest(path, payload):
    atomic_json(manifest_path(path), payload)


def artifact_info(path):
    """A origem só é reutilizada quando o manifesto pertence aos bytes atuais."""
    path = Path(path)
    digest = sha256(path)
    sidecar = manifest_path(path)
    previous = json.loads(sidecar.read_text()) if sidecar.exists() else {}
    if previous.get('sha256') != digest:
        previous = {}
    return {**previous, 'filename': path.name, 'sha256': digest, 'bytes': path.stat().st_size}


def publish_versioned(client, path, bucket, key):
    """Exige versionamento antes de sobrescrever; devolve a versão exata enviada."""
    path = Path(path)
    if client.get_bucket_versioning(Bucket=bucket).get('Status') != 'Enabled':
        client.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={'Status': 'Enabled'})
        if client.get_bucket_versioning(Bucket=bucket).get('Status') != 'Enabled':
            raise RuntimeError('Versionamento S3 não foi habilitado; upload recusado.')
    info = artifact_info(path)
    client.upload_file(str(path), bucket, key, ExtraArgs={'Metadata': {'sha256': info['sha256']}})
    remote = client.head_object(Bucket=bucket, Key=key)
    if remote['ContentLength'] != info['bytes'] or remote.get('Metadata', {}).get('sha256') != info['sha256']:
        raise RuntimeError('Objeto enviado não corresponde ao arquivo local.')
    if not remote.get('VersionId') or remote['VersionId'] == 'null':
        raise RuntimeError('Objeto sem VersionId; publicação não confirmada.')
    result = {**info, 'bucket': bucket, 'key': key, 'version_id': remote['VersionId'],
              'published_at': datetime.now(timezone.utc).isoformat()}
    write_manifest(path, result)
    # Manifesto também versionado, recuperável junto ao objeto Silver.
    client.put_object(Bucket=bucket, Key=key + '.lineage.json',
                      Body=json.dumps(result, ensure_ascii=False).encode(), ContentType='application/json')
    return result


def archive_existing(path):
    """Preserva bytes e manifesto locais antes de substituir o caminho canônico."""
    import shutil
    path = Path(path)
    if not path.is_file():
        return
    archived = path.parent / '.versions' / sha256(path) / path.name
    archived.parent.mkdir(parents=True, exist_ok=True)
    if not archived.exists():
        shutil.copy2(path, archived)
    if manifest_path(path).exists():
        shutil.copy2(manifest_path(path), manifest_path(archived))
