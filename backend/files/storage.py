"""Thin boto3 wrapper: presigning and deletion. No business logic here."""

import boto3
from botocore.client import Config as BotoConfig

from django.conf import settings


def _client(endpoint=None):
    return boto3.client(
        "s3",
        endpoint_url=endpoint or settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def presign_put(key: str, content_type: str = "") -> str:
    params = {"Bucket": settings.S3_BUCKET, "Key": key}
    if content_type:
        params["ContentType"] = content_type
    # Sign against the PUBLIC endpoint: the host is part of the signature and
    # the URL must be browser-reachable.
    return _client(settings.S3_PUBLIC_ENDPOINT).generate_presigned_url(
        "put_object", Params=params, ExpiresIn=3600,
    )


def presign_get(key: str) -> str:
    return _client(settings.S3_PUBLIC_ENDPOINT).generate_presigned_url(
        "get_object", Params={"Bucket": settings.S3_BUCKET, "Key": key}, ExpiresIn=3600,
    )


def delete_object(key: str):
    _client().delete_object(Bucket=settings.S3_BUCKET, Key=key)
