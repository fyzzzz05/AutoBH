from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


class BusyError(RuntimeError):
    pass


@contextmanager
def file_lock(path: Path):
    """A process-owned lock; kernel releases it even after an unclean exit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        os.chmod(path, 0o600)
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise BusyError("操作正在进行或后台已运行，请稍后重试") from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BusyError("操作正在进行或后台已运行，请稍后重试") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class Registry:
    """Only names and groups live here; native tools own accounts and secrets."""
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "people.json"

    def people(self) -> dict:
        return read_json(self.path, {})

    def upsert(self, username: str, name: str | None, group: str | None):
        with file_lock(self.root / "people.lock"):
            people = self.people()
            row = people.setdefault(username, {"name": "", "group": ""})
            if name is not None:
                row["name"] = name
            if group is not None:
                row["group"] = group
            atomic_json(self.path, people)

    def remove(self, username: str) -> bool:
        with file_lock(self.root / "people.lock"):
            people = self.people()
            if username not in people:
                return False
            del people[username]
            atomic_json(self.path, people)
            return True
