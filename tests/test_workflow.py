import json
import tempfile
import unittest
from pathlib import Path

from nlp_teacher_glossary_pos.repository import RecordRepository
from nlp_teacher_glossary_pos.text import normalize_text, tokenize
from nlp_teacher_glossary_pos.workflow import TextWorkflow


class TextWorkflowTests(unittest.TestCase):
    def test_normalization_and_tokenization(self):
        self.assertEqual(normalize_text("  Ａ  B\nC  "), "A B C")
        self.assertEqual(tokenize("语文课 A2。"), ["语", "文", "课", "A", "2", "。"])

    def test_ingest_persists_analysis_and_uses_newer_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = TextWorkflow(RecordRepository(Path(directory) / "records.json"))
            first = {"record_id": "lesson-1", "source": "synthetic", "revision": 1,
                     "observed_at": "2026-11-18T09:00:00Z", "text": "原稿 甲乙", "context": "课堂"}
            second = {**first, "revision": 2, "text": "修订稿 乙丙"}
            self.assertEqual(workflow.ingest([first]), {"received": 1, "stored": 1})
            workflow.ingest([second, first])
            result = workflow.list_records()[0]
            self.assertEqual(result["revision"], 2)
            self.assertEqual(result["text"], "修订稿 乙丙")
            self.assertEqual(result["analysis"]["token_count"], 5)

    def test_invalid_records_are_rejected_without_partial_write(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RecordRepository(Path(directory) / "records.json")
            workflow = TextWorkflow(repository)
            valid = {"record_id": "one", "source": "synthetic", "revision": 1,
                     "observed_at": "2026-11-18T09:00:00Z", "text": "有效文本"}
            workflow.ingest([valid])
            invalid = {**valid, "record_id": "two", "observed_at": "bad-time"}
            with self.assertRaises(ValueError):
                workflow.ingest([valid, invalid])
            self.assertEqual([row["record_id"] for row in repository.read()], ["one"])

    def test_source_filter_and_fixture_are_local(self):
        fixture = json.loads(Path("fixtures/records.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            workflow = TextWorkflow(RecordRepository(Path(directory) / "records.json"))
            workflow.ingest(fixture)
            self.assertEqual(len(workflow.list_records("school-synthetic")), 2)
            self.assertEqual(workflow.list_records("missing"), [])


if __name__ == "__main__":
    unittest.main()
