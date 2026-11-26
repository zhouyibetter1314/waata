"""Private file bytes and PostgreSQL metadata for C5/C6 evidence."""

import asyncio
import fcntl
import logging
import os
import re
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from waata.artifacts import ArtifactInput, ArtifactRef

from waata_api.repositories import PostgresRepository

from .config import DEFAULT_ARTIFACT_LIMITS, Settings

_KEY = re.compile(r"[0-9a-f]{32}(?:\.(?:png|json|zip))?")
_EXTENSIONS = {
    "application/json": ".json",
    "image/png": ".png",
    "application/zip": ".zip",
}
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunArtifactStore:
    store: "FileArtifactStore"
    run_id: str
    execution_token: str

    async def save(self, artifact: ArtifactInput) -> ArtifactRef:
        if artifact.run_id != self.run_id:
            raise ValueError("Evidence belongs to a different run")
        return await self.store.save(artifact, self.execution_token)


class FileArtifactStore:
    def __init__(
        self,
        root: Path,
        repository: PostgresRepository,
        *,
        retention_seconds: int = 7 * 24 * 60 * 60,
        limits: dict[str, int] | None = None,
        sanitize: Callable[[str], str] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._root = Path(root)
        self._pending = self._root / ".pending"
        self._repository = repository
        self._retention = timedelta(seconds=retention_seconds)
        self._limits = DEFAULT_ARTIFACT_LIMITS | (limits or {})
        self._sanitize = sanitize
        self._clock = clock
        self._writes: set[asyncio.Task[ArtifactRef]] = set()

    @classmethod
    def from_settings(
        cls, settings: Settings, repository: PostgresRepository
    ) -> "FileArtifactStore":
        return cls(
            settings.artifact_root,
            repository,
            retention_seconds=settings.artifact_retention_seconds,
            limits=settings.artifact_max_bytes,
            sanitize=settings.policy.sanitize,
        )

    def for_run(self, run_id: str, execution_token: str) -> RunArtifactStore:
        return RunArtifactStore(self, run_id, execution_token)

    def _path(self, key: str) -> Path:
        if not _KEY.fullmatch(key):
            raise ValueError("Invalid artifact storage key")
        return self._root / key

    @staticmethod
    def _read(path: Path) -> bytes:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                raise OSError("The artifact is not a regular file")
            return file.read()

    async def read(self, storage_key: str) -> bytes:
        return await asyncio.to_thread(self._read, self._path(storage_key))

    def _begin_write(self, key: str) -> BinaryIO:
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._pending.mkdir(mode=0o700, exist_ok=True)
        marker = os.fdopen(
            os.open(self._pending / key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            "wb",
        )
        try:
            fcntl.flock(marker, fcntl.LOCK_EX)
        except OSError:
            marker.close()
            raise
        return marker

    def _stage(self, key: str, content: bytes) -> None:
        temp = self._pending / f"{key}.tmp"
        with os.fdopen(
            os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        path = self._path(key)
        os.replace(temp, path)
        dir_fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def _discard_pending(self, key: str, *, keep_bytes: bool) -> None:
        if not keep_bytes:
            self._path(key).unlink(missing_ok=True)
        (self._pending / f"{key}.tmp").unlink(missing_ok=True)
        (self._pending / key).unlink(missing_ok=True)

    async def _save(self, artifact: ArtifactInput, execution_token: str) -> ArtifactRef:
        token = uuid4().hex
        key = token + _EXTENSIONS[artifact.mime_type]
        reference = ArtifactRef(
            **artifact.model_dump(exclude={"content"}),
            artifact_id=f"art_{token}",
            size_bytes=len(artifact.content),
        )
        with await asyncio.to_thread(self._begin_write, key):
            try:
                await asyncio.to_thread(self._stage, key, artifact.content)
            except Exception:
                await asyncio.to_thread(self._discard_pending, key, keep_bytes=False)
                raise

            try:
                await self._repository.register_artifact(
                    artifact.run_id,
                    execution_token,
                    {
                        **reference.model_dump(),
                        "storage_key": key,
                        "expires_at": self._clock() + self._retention,
                    },
                )
            except Exception:
                # A connection can fail after commit. Preserve the file until its
                # registration can be checked, including by the next Worker.
                try:
                    committed = await self._repository.get_artifact_by_storage_key(key)
                except Exception:
                    _LOG.warning("Evidence write status requires reconciliation")
                    raise OSError(
                        "Evidence registration could not be verified"
                    ) from None
                if committed is None:
                    await asyncio.to_thread(
                        self._discard_pending, key, keep_bytes=False
                    )
                    raise
            try:
                await asyncio.to_thread(self._discard_pending, key, keep_bytes=True)
            except OSError:
                _LOG.warning("Evidence staging marker requires reconciliation")
        return reference

    def _write_done(self, task: asyncio.Task[ArtifactRef]) -> None:
        self._writes.discard(task)
        if not task.cancelled():
            task.exception()

    async def save(self, artifact: ArtifactInput, execution_token: str) -> ArtifactRef:
        if len(artifact.content) > self._limits[artifact.kind]:
            raise ValueError("Evidence exceeds the configured size limit")
        if self._sanitize and artifact.mime_type == "application/json":
            content = artifact.content.decode("utf-8")
            if self._sanitize(content) != content:
                raise ValueError("Evidence contains a configured sensitive value")

        # An interrupted caller need not wait for file IO or a DB reply. Keep
        # the operation alive to reconcile the file; the lease fences its write.
        task = asyncio.create_task(self._save(artifact, execution_token))
        self._writes.add(task)
        task.add_done_callback(self._write_done)
        return await asyncio.shield(task)

    async def drain(self) -> None:
        if self._writes:
            await asyncio.gather(
                *(asyncio.shield(task) for task in self._writes),
                return_exceptions=True,
            )

    def _old_markers(self, limit: int) -> list[str]:
        cutoff = self._clock().timestamp() - 60
        keys = []
        if self._pending.is_dir():
            with os.scandir(self._pending) as entries:
                for entry in entries:
                    if not _KEY.fullmatch(entry.name):
                        continue
                    try:
                        changed_at = entry.stat(follow_symlinks=False).st_mtime
                    except FileNotFoundError:
                        # Another process finished or reconciled this write.
                        continue
                    if changed_at <= cutoff:
                        keys.append(entry.name)
                        if len(keys) == limit:
                            break
        return keys

    def _try_marker(self, key: str) -> BinaryIO | None:
        try:
            marker = (self._pending / key).open("rb")
        except FileNotFoundError:
            return None
        try:
            fcntl.flock(marker, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            marker.close()
            return None
        except OSError:
            marker.close()
            raise
        return marker

    def _remove_file(self, key: str, mime_type: str) -> None:
        path = self._path(key)
        if not path.suffix and mime_type in _EXTENSIONS:
            # A legacy file may also have a typed hard link for local browsing.
            linked = path.with_suffix(_EXTENSIONS[mime_type])
            try:
                if os.path.samestat(path.lstat(), linked.lstat()):
                    linked.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
        path.unlink(missing_ok=True)

    async def purge_deleted(
        self, *, run_id: str | None = None, limit: int = 100
    ) -> None:
        for row in await self._repository.deleted_artifacts(run_id=run_id, limit=limit):
            key = row["storage_key"]
            try:
                await asyncio.to_thread(self._remove_file, key, row["mime_type"])
            except (OSError, ValueError):
                _LOG.warning("Could not remove a deleted run's evidence file")
                await self._repository.finish_artifact_deletion(key, retry=True)
                continue
            await self._repository.finish_artifact_deletion(key, retry=False)

    async def purge_expired(self, *, limit: int = 100) -> None:
        for key in await asyncio.to_thread(self._old_markers, limit):
            marker = await asyncio.to_thread(self._try_marker, key)
            if marker is not None:
                with marker:
                    registered = await self._repository.get_artifact_by_storage_key(key)
                    await asyncio.to_thread(
                        self._discard_pending, key, keep_bytes=registered is not None
                    )
        for row in await self._repository.expired_artifacts(limit=limit):
            key = row["storage_key"]
            try:
                await asyncio.to_thread(self._remove_file, key, row["mime_type"])
            except (OSError, ValueError):
                _LOG.warning("Could not remove an expired evidence file")
                continue
            await self._repository.mark_artifact_purged(row["artifact_id"], key)
