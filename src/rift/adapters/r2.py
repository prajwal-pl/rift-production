"""Cloudflare R2 implementation of the `StorageProvider` port (S3 API via boto3)."""

import asyncio
import mimetypes

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from rift.config import RiftSettings

_IMMUTABLE = "public, max-age=31536000, immutable"
_NO_CACHE = "no-cache"
_PRESIGN_SECONDS = 7 * 24 * 3600  # R2 maximum


class R2StorageProvider:
    def __init__(
        self,
        *,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        public_base_url: str = "",
    ) -> None:
        self._bucket = bucket
        self._public_base_url = public_base_url.rstrip("/")
        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 5, "mode": "standard"},
                connect_timeout=10,
                read_timeout=60,
            ),
        )

    @classmethod
    def from_settings(cls, settings: RiftSettings) -> "R2StorageProvider":
        missing = [
            name
            for name, val in (
                ("R2_ACCOUNT_ID", settings.r2_account_id),
                ("R2_ACCESS_KEY", settings.r2_access_key),
                ("R2_SECRET_ACCESS_KEY", settings.r2_secret_access_key),
            )
            if not val
        ]
        if missing:
            raise RuntimeError(f"R2 is not configured; missing: {', '.join(missing)}")
        assert settings.r2_account_id and settings.r2_access_key
        assert settings.r2_secret_access_key
        return cls(
            account_id=settings.r2_account_id,
            access_key_id=settings.r2_access_key.get_secret_value(),
            secret_access_key=settings.r2_secret_access_key.get_secret_value(),
            bucket=settings.r2_bucket,
            public_base_url=settings.r2_public_base_url,
        )

    @staticmethod
    def _cache_control(path: str) -> str:
        # source.tgz is overwritten every coder round; published files never change.
        return _NO_CACHE if path.endswith("source.tgz") else _IMMUTABLE

    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        if content_type == "application/octet-stream":
            content_type = mimetypes.guess_type(path)[0] or content_type
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=path,
            Body=content,
            ContentType=content_type,
            CacheControl=self._cache_control(path),
        )
        return path

    async def get_file(self, path: str) -> bytes:
        def _download() -> bytes:
            try:
                return self._s3.get_object(Bucket=self._bucket, Key=path)["Body"].read()
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise FileNotFoundError(path) from e
                raise

        return await asyncio.to_thread(_download)

    def get_public_url(self, path: str) -> str:
        if self._public_base_url:
            return f"{self._public_base_url}/{path.lstrip('/')}"
        # No custom domain configured: fall back to a (max 7 day) presigned URL.
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": path},
            ExpiresIn=_PRESIGN_SECONDS,
        )
