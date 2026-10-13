from __future__ import annotations

import hashlib
import hmac
import mimetypes
import time
from urllib.parse import quote
from pathlib import Path
from collections.abc import Iterator
from typing import BinaryIO, Protocol


class StorageBackend(Protocol):
    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> tuple[int, str]: ...
    def get(self, key: str) -> bytes: ...
    def stream(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]: ...
    def path(self, key: str) -> Path: ...
    def url(self, key: str) -> str: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str | Path, signing_secret: str | bytes = "", route: str = "/api/v1/media"):
        self.root = Path(root).resolve()
        self.route = route.rstrip("/")
        self.signing_secret = signing_secret.encode() if isinstance(signing_secret, str) else signing_secret
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage path escapes storage root")
        return path

    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> tuple[int, str]:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        digest = hashlib.sha256()
        with path.open("wb") as target:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    path.unlink(missing_ok=True)
                    raise ValueError("Upload exceeds configured size limit")
                digest.update(chunk)
                target.write(chunk)
        return total, digest.hexdigest()

    def path(self, key: str) -> Path:
        path = self._path(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path

    def stream(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        path = self.path(key)
        with path.open("rb") as source:
            while chunk := source.read(chunk_size):
                yield chunk

    def get(self, key: str) -> bytes:
        return self.path(key).read_bytes()

    def url(self, key: str) -> str:
        # API callers receive a short-lived signed route; ownership is still
        # checked by the API before serving the object.
        if not self.signing_secret:
            return f"{self.route}/{key}"
        expires = int(time.time()) + 900
        signature = hmac.new(self.signing_secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()
        return f"{self.route}/{quote(key, safe='/')}?expires={expires}&signature={signature}"

    def verify(self, key: str, expires: int, signature: str) -> bool:
        if not self.signing_secret or expires < int(time.time()):
            return False
        expected = hmac.new(self.signing_secret, f"{key}:{expires}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class S3Storage:
    """S3-compatible adapter boundary; the API can swap it via configuration."""

    def __init__(self, client, bucket: str, public_base_url: str):
        self.client = client
        self.bucket = bucket
        self.public_base_url = public_base_url.rstrip("/")

    def put_stream(self, key: str, stream: BinaryIO, max_bytes: int) -> tuple[int, str]:
        class LimitedReader:
            def __init__(self, source: BinaryIO, limit: int):
                self.source, self.limit, self.total = source, limit, 0
                self.digest = hashlib.sha256()

            def read(self, size: int = -1) -> bytes:
                chunk = self.source.read(size)
                self.total += len(chunk)
                if self.total > self.limit:
                    raise ValueError("Upload exceeds configured size limit")
                self.digest.update(chunk)
                return chunk

        reader = LimitedReader(stream, max_bytes)
        if hasattr(self.client, "upload_fileobj"):
            self.client.upload_fileobj(reader, self.bucket, key)
        else:  # Minimal S3-compatible clients used in tests.
            data = reader.read(max_bytes + 1)
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return reader.total, reader.digest.hexdigest()

    def path(self, key: str) -> Path:
        raise NotImplementedError("S3 media is streamed through signed URLs")

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def stream(self, key: str, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
        raise NotImplementedError("S3 media is streamed by the object store")

    def url(self, key: str) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=900)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def sniff_mime(filename: str, declared: str | None, sample: bytes = b"") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    allowed = {"video/", "audio/", "image/", "text/"}
    value = declared or guessed or "application/octet-stream"
    if not any(value.startswith(prefix) for prefix in allowed):
        raise ValueError("Unsupported upload MIME type")
    detected: str | None = None
    if sample.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
    elif sample.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
    elif sample.startswith((b"GIF87a", b"GIF89a")):
        detected = "image/gif"
    elif len(sample) >= 12 and sample[4:8] == b"ftyp":
        detected = "video/mp4"
    elif sample.startswith(b"RIFF") and sample[8:12] == b"WAVE":
        detected = "audio/wav"
    elif sample.startswith(b"OggS"):
        detected = "audio/ogg"
    elif sample.startswith((b"ID3", b"\xff\xfb")):
        detected = "audio/mpeg"
    if detected and value != detected and value.split("/", 1)[0] != detected.split("/", 1)[0]:
        raise ValueError("Declared MIME type does not match file content")
    if detected:
        value = detected
    return value
