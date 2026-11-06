"""Proveniência só acompanha bytes correspondentes e exige versões S3 reais."""
import hashlib
import json
from unittest.mock import Mock

import pytest

from src.storage.artifacts import artifact_info, archive_existing, manifest_path, publish_versioned, write_manifest


def test_modified_file_does_not_inherit_previous_origin(tmp_path):
    file = tmp_path / 'silver.parquet'
    file.write_bytes(b'first')
    write_manifest(file, {**artifact_info(file), 'bronze': {'sha256': 'old'}})
    archive_existing(file)
    file.write_bytes(b'second')
    assert 'bronze' not in artifact_info(file)
    archived = file.parent / '.versions' / hashlib.sha256(b'first').hexdigest() / file.name
    assert archived.read_bytes() == b'first'
    assert json.loads(manifest_path(archived).read_text())['bronze']['sha256'] == 'old'


def test_upload_enables_versioning_before_replacing_object(tmp_path):
    file = tmp_path / 'bronze.zip'
    file.write_bytes(b'zip')
    client = Mock()
    client.get_bucket_versioning.side_effect = [{}, {'Status': 'Enabled'}]
    digest = hashlib.sha256(b'zip').hexdigest()
    client.head_object.return_value = {'ContentLength': 3, 'VersionId': 'version-2', 'Metadata': {'sha256': digest}}
    result = publish_versioned(client, file, 'bronze', 'period/file.zip')
    assert result['version_id'] == 'version-2'
    assert result['sha256'] == digest
    client.put_bucket_versioning.assert_called_once()
    assert json.loads(client.put_object.call_args.kwargs['Body'])['version_id'] == 'version-2'
    assert artifact_info(file)['version_id'] == 'version-2'


def test_versioning_failure_prevents_overwrite(tmp_path):
    file = tmp_path / 'bronze.zip'
    file.write_bytes(b'zip')
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    with pytest.raises(RuntimeError, match='Versionamento'):
        publish_versioned(client, file, 'bronze', 'period/file.zip')
    client.upload_file.assert_not_called()
