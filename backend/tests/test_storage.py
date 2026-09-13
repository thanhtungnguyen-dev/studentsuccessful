"""Tests for file storage adapter protocol and local implementation."""

import tempfile
from pathlib import Path

import pytest

from backend.app.core.storage import LocalStorageAdapter, S3StorageAdapter


class _FakeBody:
    def __init__(self, data: bytes):
        self.data = data
        self.closed = False

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        self.closed = True


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.last_body: _FakeBody | None = None

    def put_object(self, *, Bucket, Key, Body, ServerSideEncryption):
        assert ServerSideEncryption == "AES256"
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket, Key):
        self.last_body = _FakeBody(self.objects[(Bucket, Key)])
        return {"Body": self.last_body}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def head_bucket(self, *, Bucket):
        assert Bucket == "studentsuccessful-private-resumes"


def test_local_storage_adapter_lifecycle():
    """Verify save, read, health_check, and delete operations on LocalStorageAdapter."""
    with tempfile.TemporaryDirectory() as temp_dir:
        adapter = LocalStorageAdapter(temp_dir)

        # Health check
        assert adapter.health_check() is True

        # Save
        test_content = b"Resume PDF binary content mock"
        saved_key = adapter.save("resumes/student_123.pdf", test_content)
        assert saved_key == "resumes/student_123.pdf"
        assert (adapter.root_dir / saved_key).exists()

        # Open
        read_content = adapter.open("resumes/student_123.pdf")
        assert read_content == test_content

        # Delete
        adapter.delete("resumes/student_123.pdf")
        assert not (adapter.root_dir / saved_key).exists()


@pytest.mark.parametrize(
    "key",
    [
        "../../outside",
        "../outside",
        "foo/../../../outside",
        "/outside",
        r"C:\\outside",
        r"\\\\server\\share\\outside",
        r"..\\outside",
    ],
)
def test_local_storage_rejects_traversal_and_absolute_keys(key):
    """An untrusted key cannot read or delete a file outside the storage root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir) / "storage-root"
        adapter = LocalStorageAdapter(str(root))
        with pytest.raises(ValueError, match="Invalid storage key"):
            adapter.save(key, b"private")
        with pytest.raises(ValueError, match="Invalid storage key"):
            adapter.open(key)
        with pytest.raises(ValueError, match="Invalid storage key"):
            adapter.delete(key)

        # This sibling is intentionally reachable by ../outside from the adapter
        # root, but must remain untouched because the key is rejected first.
        outside = Path(temp_dir) / "outside"
        outside.write_bytes(b"do not expose or delete this")
        with pytest.raises(ValueError, match="Invalid storage key"):
            adapter.open("../outside")
        with pytest.raises(ValueError, match="Invalid storage key"):
            adapter.delete("../outside")
        assert outside.read_bytes() == b"do not expose or delete this"


def test_private_s3_storage_adapter_preserves_opaque_keys_without_public_urls():
    client = _FakeS3Client()
    adapter = S3StorageAdapter(
        "studentsuccessful-private-resumes",
        "us-east-1",
        "resumes",
        client=client,
    )

    assert adapter.health_check() is True
    assert adapter.save("versions/a.pdf", b"private resume") == "versions/a.pdf"
    assert client.objects == {
        ("studentsuccessful-private-resumes", "resumes/versions/a.pdf"): b"private resume"
    }
    assert adapter.open("versions/a.pdf") == b"private resume"
    assert client.last_body is not None and client.last_body.closed
    adapter.delete("versions/a.pdf")
    assert client.objects == {}


@pytest.mark.parametrize("key", ["../outside", "/outside", r"C:\\outside", "a/../../b"])
def test_private_s3_storage_rejects_unsafe_keys(key):
    adapter = S3StorageAdapter(
        "studentsuccessful-private-resumes",
        "us-east-1",
        "resumes",
        client=_FakeS3Client(),
    )
    with pytest.raises(ValueError, match="Invalid storage key"):
        adapter.save(key, b"private")
