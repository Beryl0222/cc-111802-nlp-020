from datetime import datetime, timezone

from .annotation import STATUS_ORDER, annotate_record, evaluate_judgment, select_snapshot
from .dictionary import (
    entries_by_term,
    get_version,
    latest_version,
    matching_senses,
    publish_version,
    retract_entry,
)
from .overrides import add_override as store_override
from .overrides import get_override, is_active
from .overrides import revoke_override as store_revoke
from .records import TextRecord
from .text import analyze, normalize_context, normalize_text


class TextWorkflow:
    """教研文本的词性标注、人工校订与句法检索。

    口径约定：词典版本、上下文标注、人工决定与句法查询共用同一个
    规范化后的语境字符串；词典更新只影响之后产生的标注快照，旧快照
    保留，按词典版本发起的旧查询可以复现。
    """

    def __init__(self, repository, now=None):
        self.repository = repository
        self._now = now or (lambda: datetime.now(timezone.utc).isoformat())

    # ---------- 状态 ----------
    def _load(self):
        return self.repository.read_state()

    def _save(self, state):
        self.repository.replace_state(state)

    def _annotate(self, record, state, dictionary_version):
        annotations = record.setdefault("annotations", [])
        annotation = annotate_record(
            record,
            state["dictionary"],
            state["overrides"],
            dictionary_version,
            self._now(),
            f"{record['record_id']}#{len(annotations) + 1}",
        )
        annotations.append(annotation)
        record["current_annotation"] = annotation["annotation_id"]
        return annotation

    # ---------- 导入 ----------
    def ingest(self, values):
        """导入文本记录并按最新词典与现行人工校订标注。

        修订号更新或正文变化的记录重新标注（旧快照随旧修订一起替换）；
        同一修订重复导入时追加一个新快照，让新导入文本用上最新词典。
        """
        if not isinstance(values, list):
            raise TypeError("导入内容必须是记录列表")
        incoming = [TextRecord.from_dict(value).to_dict() for value in values]
        state = self._load()
        current = {record["record_id"]: record for record in state["records"]}
        version = latest_version(state["dictionary"])
        version_number = version["version"] if version else 0
        for record in incoming:
            previous = current.get(record["record_id"])
            if previous is None or record["revision"] >= previous["revision"]:
                record["text"] = normalize_text(record["text"])
                record["context"] = normalize_context(record["context"])
                record["analysis"] = analyze(record)
                if (
                    previous is not None
                    and previous["revision"] == record["revision"]
                    and previous.get("text") == record["text"]
                ):
                    record["annotations"] = list(previous.get("annotations", []))
                self._annotate(record, state, version_number)
                current[record["record_id"]] = record
        state["records"] = sorted(current.values(), key=lambda row: row["record_id"])
        self._save(state)
        return {"received": len(incoming), "stored": len(state["records"])}

    # ---------- 记录查看 ----------
    def list_records(self, source=None):
        records = self._load()["records"]
        if source:
            records = [record for record in records if record["source"] == source]
        return records

    def summarize_records(self, source=None):
        state = self._load()
        summaries = []
        for record in state["records"]:
            if source and record["source"] != source:
                continue
            snapshot = select_snapshot(record)
            counts = {status: 0 for status in STATUS_ORDER}
            if snapshot is not None:
                for judgment in snapshot["judgments"]:
                    status, _ = evaluate_judgment(
                        judgment, record["context"], state["dictionary"], state["overrides"]
                    )
                    counts[status] += 1
            summaries.append(
                {
                    "record_id": record["record_id"],
                    "source": record["source"],
                    "revision": record["revision"],
                    "context": record["context"],
                    "dictionary_version": snapshot["dictionary_version"] if snapshot else None,
                    "annotation_count": len(record.get("annotations", [])),
                    "status_counts": counts,
                }
            )
        return summaries

    # ---------- 词典版本 ----------
    def publish_dictionary(self, entries, note=""):
        state = self._load()
        version = publish_version(state["dictionary"], entries, note, self._now())
        self._save(state)
        return version

    def retract_dictionary_entry(self, term, pos=None, note=""):
        state = self._load()
        version = retract_entry(state["dictionary"], term, pos, note, self._now())
        self._save(state)
        return version

    def dictionary_versions(self):
        state = self._load()
        return [
            {
                "version": version["version"],
                "published_at": version["published_at"],
                "note": version["note"],
                "entry_count": len(version["entries"]),
            }
            for version in state["dictionary"]["versions"]
        ]

    def dictionary_entries(self, version=None):
        state = self._load()
        if version is None:
            found = latest_version(state["dictionary"])
            return found["entries"] if found else []
        found = get_version(state["dictionary"], version)
        if found is None:
            raise ValueError(f"没有对应的词典版本：{version}")
        return found["entries"]

    # ---------- 人工校订 ----------
    def add_override(self, term, context, pos, teacher=""):
        state = self._load()
        override = store_override(state["overrides"], term, context, pos, teacher, self._now())
        matching = [
            record["record_id"]
            for record in state["records"]
            if record["context"] == override["context"]
            and override["term"] in record.get("analysis", {}).get("tokens", [])
        ]
        self._save(state)
        return {"override": override, "matching_records": matching}

    def revoke_override(self, override_id):
        state = self._load()
        override = store_revoke(state["overrides"], override_id, self._now())
        self._save(state)
        return override

    def list_overrides(self, active_only=False):
        overrides = self._load()["overrides"]
        if active_only:
            overrides = [override for override in overrides if is_active(override)]
        return overrides

    # ---------- 选择性重处理 ----------
    def reprocess(self, record_ids=None, source=None, context=None, term=None,
                  stale_only=False, all_records=False, dictionary_version=None):
        """按选择条件重标部分记录，适用的人工校订会重新生效，不会被覆盖。

        不指定词典版本时用最新版；也可以指定旧版本用于复现或回退。
        """
        state = self._load()
        if dictionary_version is None:
            version = latest_version(state["dictionary"])
        else:
            version = get_version(state["dictionary"], dictionary_version)
        if version is None:
            raise ValueError("没有可用的词典版本")
        if not any([record_ids, source, context, term, stale_only, all_records]):
            raise ValueError("请指定重处理范围：record_ids/source/context/term/stale_only/all_records")
        normalized_context = normalize_context(context) if context else None
        normalized_term = normalize_text(term) if term else None
        processed = []
        for record in state["records"]:
            if record_ids and record["record_id"] not in record_ids:
                continue
            if source and record["source"] != source:
                continue
            if normalized_context is not None and record["context"] != normalized_context:
                continue
            if normalized_term is not None and normalized_term not in record.get("analysis", {}).get("tokens", []):
                continue
            if stale_only and not self._has_stale(record, state):
                continue
            annotation = self._annotate(record, state, version["version"])
            processed.append({"record_id": record["record_id"], "annotation_id": annotation["annotation_id"]})
        self._save(state)
        return {"dictionary_version": version["version"], "reprocessed": processed, "count": len(processed)}

    def _has_stale(self, record, state):
        snapshot = select_snapshot(record)
        if snapshot is None:
            return True
        return any(
            evaluate_judgment(judgment, record["context"], state["dictionary"], state["overrides"])[0] == "stale"
            for judgment in snapshot["judgments"]
        )

    # ---------- 句法检索 ----------
    def query(self, pos=None, term=None, source=None, context=None,
              dictionary_version=None, include_stale=False, status=None):
        """句法检索。默认取各记录当前快照并排除已过期的标注；指定词典

        版本则按该版本的快照复现旧查询（过期标记仍按当前知识标注）。
        """
        state = self._load()
        normalized_context = normalize_context(context) if context else None
        normalized_term = normalize_text(term) if term else None
        results = []
        for record in state["records"]:
            if source and record["source"] != source:
                continue
            if normalized_context is not None and record["context"] != normalized_context:
                continue
            snapshot = select_snapshot(record, dictionary_version)
            if snapshot is None:
                continue
            for judgment in snapshot["judgments"]:
                if normalized_term is not None and judgment["token"] != normalized_term:
                    continue
                if pos and judgment["pos"] != pos:
                    continue
                evaluated, reason = evaluate_judgment(
                    judgment, record["context"], state["dictionary"], state["overrides"]
                )
                if status and evaluated != status:
                    continue
                if evaluated == "stale" and not include_stale:
                    continue
                results.append(
                    {
                        "record_id": record["record_id"],
                        "context": record["context"],
                        "index": judgment["index"],
                        "token": judgment["token"],
                        "pos": judgment["pos"],
                        "basis": judgment["basis"],
                        "origin": judgment["origin"],
                        "status": evaluated,
                        "status_reason": reason,
                        "dictionary_version": snapshot["dictionary_version"],
                        "annotation_id": snapshot["annotation_id"],
                    }
                )
        return results

    # ---------- 溯源 ----------
    def explain(self, record_id, index=None, token=None):
        """查看词性判断来自哪版词典、哪个义项、哪条人工校订及其现状。"""
        state = self._load()
        record = next((row for row in state["records"] if row["record_id"] == record_id), None)
        if record is None:
            raise ValueError(f"没有这条文本记录：{record_id}")
        snapshot = select_snapshot(record)
        if snapshot is None:
            raise ValueError(f"记录尚未标注：{record_id}")
        normalized_token = normalize_text(token) if token else None
        entries = entries_by_term(get_version(state["dictionary"], snapshot["dictionary_version"]))
        details = []
        for judgment in snapshot["judgments"]:
            if index is not None and judgment["index"] != index:
                continue
            if normalized_token is not None and judgment["token"] != normalized_token:
                continue
            evaluated, reason = evaluate_judgment(
                judgment, record["context"], state["dictionary"], state["overrides"]
            )
            details.append(
                {
                    "index": judgment["index"],
                    "token": judgment["token"],
                    "pos": judgment["pos"],
                    "basis": judgment["basis"],
                    "resolution": judgment["resolution"],
                    "status": evaluated,
                    "status_reason": reason,
                    "dictionary_version": snapshot["dictionary_version"],
                    "annotation_id": snapshot["annotation_id"],
                    "annotated_at": snapshot["annotated_at"],
                    "sense": self._sense_detail(entries, judgment, record["context"]),
                    "override": get_override(state["overrides"], judgment["override_id"])
                    if judgment["basis"] == "manual"
                    else None,
                    "candidates": judgment["candidates"],
                }
            )
        return {
            "record_id": record_id,
            "context": record["context"],
            "text": record["text"],
            "dictionary_version": snapshot["dictionary_version"],
            "judgments": details,
        }

    @staticmethod
    def _sense_detail(entries, judgment, context):
        if judgment["basis"] != "dictionary":
            return None
        entry = entries.get(judgment["token"])
        for sense in matching_senses(entry, context):
            if sense["pos"] == judgment["pos"]:
                return sense
        return None
