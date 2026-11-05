import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from google.api_core.exceptions import PreconditionFailed

from scripts import gcs_sync as sync


class HistorySyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.local = self.root / "public" / "data" / "custom.json"
        self.archive = self.local.with_name("custom.json.archive.json")
        self.key = "custom/news.json"
        self.archive_key = self.key + ".archive.json"
        self.objects = {}
        self.writes = []
        bucket = Mock()
        bucket.get_blob.side_effect = self.get_blob
        bucket.blob.side_effect = self.blob
        for change in (
            patch.object(sync, "_bucket", return_value=bucket),
            patch.object(sync, "OBJECT", self.key),
            patch.object(sync, "LOCAL_PATH", self.local),
            patch.object(sync, "_generation_path", return_value=self.root / "receipt"),
        ):
            change.start()
            self.addCleanup(change.stop)

    def get_blob(self, key):
        return self.blob(key) if key in self.objects else None

    def blob(self, key):
        generation, value = self.objects.get(key, (0, ""))
        blob = Mock(generation=generation)

        def download(path, *, if_generation_match):
            self.assertEqual(if_generation_match, generation)
            Path(path).write_text(value, encoding="utf-8")

        def upload(path, *, content_type, if_generation_match):
            self.assertTrue(content_type.startswith("application/json"))
            if if_generation_match != generation:
                raise PreconditionFailed(key)
            blob.generation = generation + 1
            self.objects[key] = (blob.generation, Path(path).read_text(encoding="utf-8"))
            self.writes.append(key)

        blob.download_to_filename.side_effect = download
        blob.upload_from_filename.side_effect = upload
        return blob

    def test_legacy_state_round_trips_history_with_custom_paths(self):
        self.objects[self.key] = (8, '[{"id":"old"}]')
        sync.download()
        self.assertEqual(json.loads(self.local.read_text()), [{"id": "old"}])
        self.assertEqual(json.loads(self.archive.read_text()), [])
        self.archive.write_text('["evicted"]', encoding="utf-8")
        self.local.write_text('[{"id":"new"}]', encoding="utf-8")
        sync.upload()
        self.assertEqual(self.writes, [self.archive_key, self.key])
        self.archive.unlink()
        sync.download()
        self.assertEqual(json.loads(self.archive.read_text()), ["evicted"])
        self.assertEqual(json.loads(self.local.read_text()), [{"id": "new"}])

    def test_concurrent_history_update_prevents_stale_publication(self):
        sync.download()
        self.objects[self.archive_key] = (1, '["other-job"]')
        with self.assertRaises(PreconditionFailed):
            sync.upload()
        self.assertEqual(self.writes, [])
        self.assertEqual(self.objects[self.archive_key], (1, '["other-job"]'))

    def test_empty_bucket_preserves_local_seed(self):
        self.local.parent.mkdir(parents=True)
        self.local.write_text('[{"id":"seed"}]', encoding="utf-8")
        self.archive.write_text('["older"]', encoding="utf-8")
        sync.download()
        sync.upload()
        self.assertEqual(json.loads(self.objects[self.key][1]), [{"id": "seed"}])
        self.assertEqual(json.loads(self.objects[self.archive_key][1]), ["older"])

    def test_state_conflict_preserves_archived_keys_and_newer_publication(self):
        self.objects[self.key] = (1, '[{"id":"old"}]')
        sync.download()
        self.archive.write_text('["old"]', encoding="utf-8")
        self.objects[self.key] = (2, '[{"id":"other-job"}]')
        with self.assertRaises(PreconditionFailed):
            sync.upload()
        self.assertEqual(self.objects[self.key], (2, '[{"id":"other-job"}]'))
        sync.download()
        self.assertEqual(json.loads(self.archive.read_text()), ["old"])
        self.assertEqual(json.loads(self.local.read_text()), [{"id": "other-job"}])

    def test_unpaired_upload_only_initializes_new_state(self):
        self.local.parent.mkdir(parents=True)
        self.local.write_text("[]", encoding="utf-8")
        sync.upload()
        self.assertEqual(self.objects[self.key], (1, "[]"))
        (self.root / "receipt").unlink()
        with self.assertRaisesRegex(RuntimeError, "Download"):
            sync.upload()
