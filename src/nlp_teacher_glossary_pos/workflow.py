from .records import TextRecord
from .text import annotate, normalize_text


class TextWorkflow:
    def __init__(self, repository):
        self.repository = repository

    def ingest(self, values):
        if not isinstance(values, list):
            raise TypeError("导入内容必须是记录列表")
        incoming = [TextRecord.from_dict(value).to_dict() for value in values]
        existing = self.repository.read()
        current = {record["record_id"]: record for record in existing}
        for record in incoming:
            previous = current.get(record["record_id"])
            if previous is None or record["revision"] >= previous["revision"]:
                normalized = normalize_text(record["text"])
                record["text"] = normalized
                record["analysis"] = annotate(record)
                current[record["record_id"]] = record
        result = sorted(current.values(), key=lambda row: row["record_id"])
        self.repository.replace(result)
        return {"received": len(incoming), "stored": len(result)}

    def list_records(self, source=None):
        records = self.repository.read()
        if source:
            records = [record for record in records if record["source"] == source]
        return records
