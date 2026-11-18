import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from nlp_teacher_glossary_pos import cli
from nlp_teacher_glossary_pos.repository import RecordRepository
from nlp_teacher_glossary_pos.workflow import TextWorkflow

NOW = "2026-11-18T12:00:00+00:00"

ENTRIES_V1 = [
    {"term": "之", "senses": [
        {"pos": "助词", "contexts": ["古文"], "origin": "general", "note": "结构助词"},
        {"pos": "动词", "contexts": ["古文"], "origin": "general", "note": "往、到"},
    ]},
    {"term": "其", "senses": [
        {"pos": "代词", "contexts": ["古文"], "origin": "general"},
        {"pos": "副词", "contexts": ["古文"], "origin": "school", "note": "校本：表推测"},
    ]},
    {"term": "说", "senses": [{"pos": "动词", "origin": "general"}]},
]


def make_workflow(directory):
    return TextWorkflow(RecordRepository(Path(directory) / "state.json"), now=lambda: NOW)


def make_record(record_id, text, context, revision=1):
    return {
        "record_id": record_id,
        "source": "school-synthetic",
        "revision": revision,
        "observed_at": "2026-11-18T10:00:00Z",
        "text": text,
        "context": context,
    }


def judgment_of(workflow, record_id, token):
    return workflow.explain(record_id, token=token)["judgments"][0]


class ProvenanceTests(unittest.TestCase):
    def test_school_sense_wins_and_explain_shows_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1, note="初版")
            workflow.ingest([make_record("cls-1", "其恕乎。", "古文")])
            detail = judgment_of(workflow, "cls-1", "其")
            self.assertEqual(detail["pos"], "副词")
            self.assertEqual(detail["basis"], "dictionary")
            self.assertEqual(detail["status"], "current")
            self.assertEqual(detail["dictionary_version"], 1)
            self.assertEqual(detail["sense"]["origin"], "school")
            self.assertEqual(detail["sense"]["note"], "校本：表推测")

    def test_ambiguous_token_is_not_silently_decided(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "学而时习之。", "古文")])
            detail = judgment_of(workflow, "cls-1", "之")
            self.assertIsNone(detail["pos"])
            self.assertEqual(detail["resolution"], "ambiguous")
            self.assertEqual([item["pos"] for item in detail["candidates"]], ["动词", "助词"])


class OverrideTests(unittest.TestCase):
    def test_override_resolves_ambiguity_and_survives_dictionary_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "学而时习之。", "古文")])
            result = workflow.add_override("之", "古文", "助词", teacher="王老师")
            self.assertEqual(result["override"]["override_id"], "ov-1")
            self.assertEqual(result["matching_records"], ["cls-1"])
            workflow.reprocess(term="之")
            detail = judgment_of(workflow, "cls-1", "之")
            self.assertEqual((detail["pos"], detail["basis"], detail["status"]), ("助词", "manual", "confirmed"))
            self.assertEqual(detail["override"]["teacher"], "王老师")
            # 词典升级并整体重处理后，相同词项与语境的人工校订仍然保留
            workflow.publish_dictionary(ENTRIES_V1 + [{"term": "道", "senses": [{"pos": "名词"}]}])
            workflow.reprocess(all_records=True)
            detail = judgment_of(workflow, "cls-1", "之")
            self.assertEqual((detail["pos"], detail["basis"], detail["status"]), ("助词", "manual", "confirmed"))
            self.assertEqual(detail["dictionary_version"], 2)

    def test_override_is_bound_to_context(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.add_override("之", "古文", "助词")
            workflow.ingest([
                make_record("cls-1", "学而时习之。", "古文"),
                make_record("exp-1", "总而言之。", "现代说明文"),
            ])
            # 语境不同，校订不适用：现代说明文中的“之”没有匹配义项
            detail = judgment_of(workflow, "exp-1", "之")
            self.assertEqual((detail["pos"], detail["resolution"]), (None, "unknown"))
            self.assertEqual(len(workflow.query(pos="助词")), 1)
            # 同一记录的语境变化后，原校订不能盲目沿用
            workflow.ingest([make_record("cls-1", "学而时习之。", "现代说明文", revision=2)])
            detail = judgment_of(workflow, "cls-1", "之")
            self.assertEqual((detail["pos"], detail["basis"]), (None, "none"))
            self.assertEqual(workflow.query(pos="助词"), [])

    def test_revoked_override_is_no_longer_confirmed(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "学而时习之。", "古文")])
            workflow.add_override("之", "古文", "助词")
            workflow.reprocess(all_records=True)
            self.assertEqual(len(workflow.query(pos="助词")), 1)
            workflow.revoke_override("ov-1")
            self.assertEqual(workflow.query(pos="助词"), [])
            stale = workflow.query(pos="助词", include_stale=True)
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0]["status"], "stale")
            self.assertIn("撤销", stale[0]["status_reason"])

    def test_new_override_supersedes_previous_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "学而时习之。", "古文")])
            workflow.add_override("之", "古文", "助词")
            workflow.reprocess(all_records=True)
            workflow.add_override("之", "古文", "代词")
            overrides = workflow.list_overrides()
            self.assertEqual(overrides[0]["superseded_by"], "ov-2")
            # 旧校订支撑的判断显露过期，不再被当成已确认标注
            stale = workflow.query(pos="助词", include_stale=True)
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0]["status"], "stale")
            workflow.reprocess(all_records=True)
            detail = judgment_of(workflow, "cls-1", "之")
            self.assertEqual((detail["pos"], detail["status"]), ("代词", "confirmed"))


class RetractionTests(unittest.TestCase):
    def test_retracted_entry_marks_dependent_annotations_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "其恕乎。", "古文")])
            self.assertEqual(len(workflow.query(pos="副词")), 1)
            version = workflow.retract_dictionary_entry("其", pos="副词")
            self.assertEqual(version["version"], 2)
            # 过期标注默认不参与检索，也不能再被当成已确认标注
            self.assertEqual(workflow.query(pos="副词"), [])
            stale = workflow.query(pos="副词", include_stale=True)
            self.assertEqual(len(stale), 1)
            self.assertEqual(stale[0]["status"], "stale")
            self.assertIn("撤回", stale[0]["status_reason"])
            # 选择性重处理只更新受影响的记录
            result = workflow.reprocess(stale_only=True)
            self.assertEqual(result["count"], 1)
            detail = judgment_of(workflow, "cls-1", "其")
            self.assertEqual((detail["pos"], detail["status"]), ("代词", "current"))
            self.assertEqual(detail["dictionary_version"], 2)
            # 旧查询按词典版本复现：仍能看到第 1 版下的判断
            old = workflow.query(pos="副词", dictionary_version=1, include_stale=True)
            self.assertEqual(len(old), 1)
            self.assertEqual(old[0]["dictionary_version"], 1)

    def test_retract_whole_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "其恕乎。", "古文")])
            workflow.retract_dictionary_entry("其")
            stale = workflow.query(term="其", include_stale=True)
            self.assertEqual([item["status"] for item in stale], ["stale"])
            with self.assertRaises(ValueError):
                workflow.retract_dictionary_entry("其")


class ReprocessTests(unittest.TestCase):
    def test_reprocess_is_selective(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([
                make_record("cls-1", "其恕乎。", "古文"),
                make_record("cls-2", "说清楚了。", "古文"),
            ])
            workflow.publish_dictionary(ENTRIES_V1 + [{"term": "道", "senses": [{"pos": "名词"}]}])
            result = workflow.reprocess(record_ids=["cls-1"])
            self.assertEqual(result["dictionary_version"], 2)
            summaries = {item["record_id"]: item for item in workflow.summarize_records()}
            self.assertEqual(summaries["cls-1"]["dictionary_version"], 2)
            self.assertEqual(summaries["cls-1"]["annotation_count"], 2)
            # 未选中的记录保持原快照，旧语料仍按原词性检索
            self.assertEqual(summaries["cls-2"]["dictionary_version"], 1)
            self.assertEqual(summaries["cls-2"]["annotation_count"], 1)

    def test_reprocess_requires_a_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            with self.assertRaises(ValueError):
                workflow.reprocess()

    def test_reprocess_can_pin_an_older_dictionary_version(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            workflow.publish_dictionary(ENTRIES_V1)
            workflow.ingest([make_record("cls-1", "其恕乎。", "古文")])
            workflow.retract_dictionary_entry("其", pos="副词")
            workflow.reprocess(all_records=True, dictionary_version=1)
            detail = judgment_of(workflow, "cls-1", "其")
            self.assertEqual((detail["pos"], detail["dictionary_version"]), ("副词", 1))


class ValidationTests(unittest.TestCase):
    def test_dictionary_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            with self.assertRaises(ValueError):
                workflow.publish_dictionary([{"term": "之", "senses": [{"pos": "助词"}]},
                                             {"term": "之", "senses": [{"pos": "动词"}]}])
            with self.assertRaises(ValueError):
                workflow.publish_dictionary([{"term": "说明", "senses": [{"pos": "动词"}]}])
            with self.assertRaises(ValueError):
                workflow.publish_dictionary([{"term": "之", "senses": [{"pos": ""}]}])
            with self.assertRaises(ValueError):
                workflow.publish_dictionary([{"term": "之", "senses": [{"pos": "助词", "origin": "unknown"}]}])

    def test_override_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            workflow = make_workflow(directory)
            with self.assertRaises(ValueError):
                workflow.add_override("说明", "古文", "动词")
            with self.assertRaises(ValueError):
                workflow.add_override("之", "古文", "")
            with self.assertRaises(ValueError):
                workflow.revoke_override("ov-9")


class RepositoryTests(unittest.TestCase):
    def test_legacy_state_file_gains_new_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            legacy = {"records": [dict(make_record("cls-1", "其恕乎。", "古文"), analysis={"tokens": []})]}
            path.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            workflow = TextWorkflow(RecordRepository(path), now=lambda: NOW)
            state = workflow.repository.read_state()
            self.assertEqual(state["dictionary"], {"versions": []})
            self.assertEqual(state["overrides"], [])
            workflow.publish_dictionary(ENTRIES_V1)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(saved["records"]), 1)
            self.assertEqual(len(saved["dictionary"]["versions"]), 1)


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(argv)
        return json.loads(buffer.getvalue())

    def test_cli_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.json")
            dictionary_path = Path(directory) / "dictionary.json"
            dictionary_path.write_text(json.dumps({"entries": ENTRIES_V1}, ensure_ascii=False), encoding="utf-8")
            records_path = Path(directory) / "records.json"
            records_path.write_text(json.dumps([make_record("cls-1", "其恕乎。", "古文")], ensure_ascii=False),
                                    encoding="utf-8")
            published = self.run_cli(["--state", state, "publish-dict", str(dictionary_path)])
            self.assertEqual(published["version"], 1)
            self.run_cli(["--state", state, "ingest", str(records_path)])
            summaries = self.run_cli(["--state", state, "list"])
            self.assertEqual(summaries[0]["status_counts"]["current"], 1)
            matches = self.run_cli(["--state", state, "query", "--pos", "副词"])
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["origin"], "school")
            detail = self.run_cli(["--state", state, "explain", "cls-1", "--token", "其"])
            self.assertEqual(detail["judgments"][0]["sense"]["note"], "校本：表推测")


if __name__ == "__main__":
    unittest.main()
