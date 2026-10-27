"""Inicialização do armazenamento sem acessar serviços externos."""

from unittest.mock import Mock, call

import pytest
from botocore.exceptions import ClientError

from src.storage.initialize_buckets import initialize_buckets


def test_existing_buckets_are_preserved():
    client = Mock()
    assert initialize_buckets(client) == []
    assert client.head_bucket.call_args_list == [
        call(Bucket="ecommerce-bronze"), call(Bucket="ecommerce-silver"),
    ]
    client.create_bucket.assert_not_called()


def test_missing_bucket_is_created():
    client = Mock()
    client.head_bucket.side_effect = [
        ClientError({"Error": {"Code": "404"}}, "HeadBucket"), None,
    ]
    assert initialize_buckets(client) == ["ecommerce-bronze"]
    client.create_bucket.assert_called_once_with(Bucket="ecommerce-bronze")


def test_permission_error_does_not_create_bucket():
    client = Mock()
    client.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "403"}}, "HeadBucket",
    )
    with pytest.raises(ClientError):
        initialize_buckets(client)
    client.create_bucket.assert_not_called()
