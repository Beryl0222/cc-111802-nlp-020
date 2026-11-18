import copy
import json
from pathlib import Path


DEFAULT_STATE = {
    "records": [],
    "dictionary": {"versions": []},
    "overrides": [],
}


class RecordRepository:
    """本地 JSON 状态库：文本记录、词典版本与人工校订存于同一文件。"""

    def __init__(self, path):
        self.path = Path(path)

    def read_state(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return copy.deepcopy(DEFAULT_STATE)
        if not isinstance(value, dict) or not isinstance(value.get("records"), list):
            raise ValueError("记录库格式无效")
        state = copy.deepcopy(DEFAULT_STATE)
        state["records"] = value["records"]
        if "dictionary" in value:
            dictionary = value["dictionary"]
            if not isinstance(dictionary, dict) or not isinstance(dictionary.get("versions"), list):
                raise ValueError("记录库格式无效：词典版本缺失")
            state["dictionary"] = dictionary
        if "overrides" in value:
            if not isinstance(value["overrides"], list):
                raise ValueError("记录库格式无效：人工校订缺失")
            state["overrides"] = value["overrides"]
        return state

    def read(self):
        return self.read_state()["records"]

    def replace_state(self, state):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "records": state.get("records", []),
            "dictionary": state.get("dictionary", {"versions": []}),
            "overrides": state.get("overrides", []),
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def replace(self, records):
        state = self.read_state()
        state["records"] = records
        self.replace_state(state)
