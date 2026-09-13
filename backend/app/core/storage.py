"""Resume storage adapters for local development and private object storage."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

from backend.app.core.config import settings


def _validated_relative_key(storage_key: str) -> PurePosixPath:
    if not isinstance(storage_key, str) or not storage_key or "\x00" in storage_key:
        raise ValueError("Invalid storage key")
    if "\\" in storage_key:
        raise ValueError("Invalid storage key")
    posix_key = PurePosixPath(storage_key)
    windows_key = PureWindowsPath(storage_key)
    if (
        posix_key.is_absolute()
        or windows_key.is_absolute()
        or any(part in {"", ".", ".."} for part in posix_key.parts)
    ):
        raise ValueError("Invalid storage key")
    return posix_key


class StorageAdapter(Protocol):
    """Abstract protocol for file storage (local filesystem, S3, etc.)."""

    def save(self, storage_key: str, data: bytes) -> str:
        """Saves file bytes and returns the opaque stored key."""
        ...

    def open(self, storage_key: str) -> bytes:
        """Reads file bytes from storage."""
        ...

    def delete(self, storage_key: str) -> None:
        """Deletes file from storage."""
        ...

    def health_check(self) -> bool:
        """Verifies read/write access to storage backend."""
        ...


class LocalStorageAdapter:
    """Local filesystem implementation of StorageAdapter for development and testing."""

    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _full_path(self, storage_key: str) -> Path:
        """Resolve only server-generated, POSIX-relative object keys under the root."""
        posix_key = _validated_relative_key(storage_key)
        candidate = (self.root_dir / posix_key).resolve()
        try:
            candidate.relative_to(self.root_dir)
        except ValueError as error:
            raise ValueError("Invalid storage key") from error
        return candidate

    def save(self, storage_key: str, data: bytes) -> str:
        target = self._full_path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as f:
            f.write(data)
        return storage_key

    def open(self, storage_key: str) -> bytes:
        target = self._full_path(storage_key)
        if not target.is_file():
            raise FileNotFoundError("Stored file not found")
        with target.open("rb") as f:
            return f.read()

    def delete(self, storage_key: str) -> None:
        target = self._full_path(storage_key)
        if target.exists():
            target.unlink()

    def health_check(self) -> bool:
        try:
            test_file = self.root_dir / ".healthcheck"
            with test_file.open("w") as f:
                f.write("ok")
            if test_file.exists():
                test_file.unlink()
            return True
        except Exception:
            return False


class S3StorageAdapter:
    """Private S3-compatible storage with the same opaque-key contract as local disk.

    The caller supplies only a server-generated storage key. Buckets must remain
    private; retrieval always flows through the authenticated application.
    """

    def __init__(
        self,
        bucket: str,
        region: str,
        prefix: str,
        *,
        endpoint_url: str | None = None,
        client=None,
    ) -> None:
        self.bucket = bucket
        self.region = region
        self.prefix = prefix.strip("/")
        self._validate_key_prefix()
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - build dependency guard
                raise RuntimeError("S3 storage requires boto3") from exc
            client = boto3.client(
                "s3",
                region_name=self.region,
                endpoint_url=endpoint_url,
            )
        self.client = client

    def _validate_key_prefix(self) -> None:
        if not self.prefix or "\\" in self.prefix:
            raise ValueError("Invalid storage prefix")
        path = PurePosixPath(self.prefix)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("Invalid storage prefix")

    def _object_key(self, storage_key: str) -> str:
        return f"{self.prefix}/{_validated_relative_key(storage_key).as_posix()}"

    def save(self, storage_key: str, data: bytes) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._object_key(storage_key),
            Body=data,
            ServerSideEncryption="AES256",
        )
        return storage_key

    def open(self, storage_key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._object_key(storage_key))
        body = response["Body"]
        try:
            return body.read()
        finally:
            close = getattr(body, "close", None)
            if close is not None:
                close()

    def delete(self, storage_key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=self._object_key(storage_key))

    def health_check(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


def get_storage_adapter() -> StorageAdapter:
    """Return the configured storage adapter without exposing storage paths to callers."""
    if settings.STORAGE_BACKEND == "local":
        return LocalStorageAdapter(settings.STORAGE_LOCAL_ROOT)
    if settings.STORAGE_BACKEND == "s3":
        return S3StorageAdapter(
            settings.STORAGE_S3_BUCKET,
            settings.STORAGE_S3_REGION,
            settings.STORAGE_S3_PREFIX,
            endpoint_url=settings.STORAGE_S3_ENDPOINT_URL,
        )
    raise RuntimeError("Configured storage backend is unavailable")
