import argparse
import json
from pathlib import Path

from .repository import RecordRepository
from .workflow import TextWorkflow


def main():
    parser = argparse.ArgumentParser(description="本地教研文本处理工具")
    parser.add_argument("action", choices=("ingest", "list"))
    parser.add_argument("path", nargs="?", default="fixtures/records.json")
    parser.add_argument("--state", default="var/records.json")
    args = parser.parse_args()
    workflow = TextWorkflow(RecordRepository(args.state))
    if args.action == "ingest":
        result = workflow.ingest(json.loads(Path(args.path).read_text(encoding="utf-8")))
    else:
        result = workflow.list_records()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
