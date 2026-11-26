"""C5/C6 byte publication and recovery across an ambiguous metadata commit."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase

from waata.artifacts import ArtifactInput
from waata_api.infrastructure.artifacts import FileArtifactStore


class Registry:
    def __init__(self):
        self.rows = {}
        self.delay_visibility = False
        self.reject_registration = False
        self.expired = False

    async def register_artifact(self, run_id, execution_token, artifact):
        if self.reject_registration:
            raise OSError("Metadata write failed")
        self.rows[artifact["storage_key"]] = artifact
        if self.delay_visibility:
            raise OSError("Commit response failed")

    async def get_artifact_by_storage_key(self, key):
        if self.delay_visibility:
            raise OSError("The registry is unreachable")
        return self.rows.get(key)

    async def expired_artifacts(self, *, limit):
        return list(self.rows.values())[:limit] if self.expired else []

    async def mark_artifact_purged(self, artifact_id, key):
        self.rows[key]["purged_at"] = datetime.now(UTC)
        return True


class ArtifactStoreTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.registry = Registry()
        self.store = FileArtifactStore(self.root, self.registry)
        self.artifact = ArtifactInput(
            run_id="run-fixture",
            kind="observation",
            mime_type="application/json",
            captured_at=datetime.now(UTC),
            content=b'{"visible":true}',
        )
        self.run_store = self.store.for_run(self.artifact.run_id, "fixture-execution")

    async def test_failed_registration_removes_unpublished_file(self):
        self.registry.reject_registration = True
        with self.assertRaises(OSError):
            await self.run_store.save(self.artifact)
        self.assertEqual(list(self.root.rglob("*")), [self.root / ".pending"])
        self.assertEqual(self.registry.rows, {})

    async def test_saves_evidence_with_a_suffix_matching_its_media_type(self):
        for kind, mime_type, suffix in (
            ("observation", "application/json", ".json"),
            ("screenshot", "image/png", ".png"),
            ("playwright_trace", "application/zip", ".zip"),
            ("test_report", "application/json", ".json"),
        ):
            with self.subTest(kind=kind):
                artifact = ArtifactInput(
                    **self.artifact.model_dump(exclude={"kind", "mime_type"}),
                    kind=kind,
                    mime_type=mime_type,
                )
                reference = await self.run_store.save(artifact)
                self.assertRegex(reference.artifact_id, r"^art_[0-9a-f]{32}$")
                key = reference.artifact_id.removeprefix("art_") + suffix
                self.assertIn(key, self.registry.rows)
                self.assertEqual(await self.store.read(key), artifact.content)
                self.assertEqual((self.root / key).read_bytes(), artifact.content)

    async def test_reads_and_purges_legacy_evidence_with_a_typed_link(self):
        key = "a" * 32
        legacy = self.root / key
        legacy.write_bytes(self.artifact.content)
        linked = legacy.with_suffix(".json")
        os.link(legacy, linked)
        self.registry.rows[key] = {
            "artifact_id": f"art_{key}",
            "storage_key": key,
            "mime_type": self.artifact.mime_type,
        }
        self.assertEqual(await self.store.read(key), self.artifact.content)
        self.registry.expired = True
        await self.store.purge_expired()
        self.assertFalse(legacy.exists())
        self.assertFalse(linked.exists())
        self.assertIsNotNone(self.registry.rows[key]["purged_at"])

    async def test_ambiguous_commit_preserves_bytes_until_reconciled(self):
        self.registry.delay_visibility = True
        with self.assertRaises(OSError):
            await self.run_store.save(self.artifact)
        key = next(iter(self.registry.rows))
        pending = self.root / ".pending" / key
        past = (datetime.now(UTC) - timedelta(minutes=2)).timestamp()
        os.utime(pending, (past, past))
        self.registry.delay_visibility = False

        await self.store.purge_expired()
        self.assertFalse(pending.exists())
        self.assertEqual(await self.store.read(key), self.artifact.content)

        self.registry.expired = True
        await self.store.purge_expired()
        self.assertIsNotNone(self.registry.rows[key]["purged_at"])
        with self.assertRaises(FileNotFoundError):
            await self.store.read(key)

    async def test_size_and_run_boundary_precede_registration(self):
        with self.assertRaises(ValueError):
            await self.store.for_run("another-run", "fixture-execution").save(
                self.artifact
            )
        bounded = FileArtifactStore(self.root, self.registry, limits={"observation": 1})
        with self.assertRaises(ValueError):
            await bounded.save(self.artifact, "fixture-execution")
        with self.assertRaises(ValueError):
            await self.store.read("../outside")
        self.assertEqual(self.registry.rows, {})
