"""Idempotent bucket creation, run at container startup."""

import boto3
from botocore.exceptions import ClientError

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ensure the S3 bucket exists (idempotent)"

    def handle(self, *args, **options):
        s3 = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1",
        )
        try:
            s3.head_bucket(Bucket=settings.S3_BUCKET)
            self.stdout.write(f"bucket {settings.S3_BUCKET!r} already exists")
        except ClientError:
            s3.create_bucket(Bucket=settings.S3_BUCKET)
            self.stdout.write(self.style.SUCCESS(f"created bucket {settings.S3_BUCKET!r}"))
