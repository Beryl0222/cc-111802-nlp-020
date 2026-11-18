import json
from pathlib import Path


class RecordRepository:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(value, dict) or not isinstance(value.get("records"), list):
            raise ValueError("记录库格式无效")
        return value["records"]

    def replace(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps({"records": records}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)
