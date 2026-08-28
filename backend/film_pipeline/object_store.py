"""Small private, content-addressed artifact store for a single Windows node."""
from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path


class LocalObjectStore:
    """Atomic SHA-256 addressed blobs; metadata/access control stay in SQLite."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key_for(payload: bytes, suffix: str = ".bin") -> tuple[str, str]:
        digest = hashlib.sha256(payload).hexdigest()
        suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return digest, f"sha256/{digest[:2]}/{digest}{suffix.lower()}"

    def path_for(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root != candidate and self.root not in candidate.parents:
            raise ValueError("object key escapes managed artifact root")
        return candidate

    def put(self, payload: bytes, *, suffix: str = ".bin") -> tuple[str, str, Path]:
        digest, key = self.key_for(payload, suffix)
        destination = self.path_for(key)
        if destination.exists():
            return digest, key, destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temporary, "xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.replace(temporary, destination)
            except FileExistsError:
                # Another worker stored identical content first.
                pass
        finally:
            temporary.unlink(missing_ok=True)
        return digest, key, destination

