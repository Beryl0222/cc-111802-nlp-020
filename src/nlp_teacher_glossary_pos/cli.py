import argparse
import json
from pathlib import Path

from .repository import RecordRepository
from .workflow import TextWorkflow


def build_parser():
    parser = argparse.ArgumentParser(description="本地教研文本词性校订工具")
    parser.add_argument("--state", default="var/records.json", help="运行数据文件路径")
    sub = parser.add_subparsers(dest="action", required=True)

    ingest = sub.add_parser("ingest", help="导入文本记录并按最新词典标注")
    ingest.add_argument("path", nargs="?", default="fixtures/records.json")

    list_cmd = sub.add_parser("list", help="查看文本记录与标注状态汇总")
    list_cmd.add_argument("--source")

    publish = sub.add_parser("publish-dict", help="发布新词典版本（只影响之后标注的文本）")
    publish.add_argument("path", nargs="?", default="fixtures/dictionary.json")
    publish.add_argument("--note", default="")

    show = sub.add_parser("show-dict", help="查看词典版本与词条")
    show.add_argument("--version", type=int)

    retract = sub.add_parser("retract", help="撤回词项或指定词性义项（以新版本发布，旧版本保留）")
    retract.add_argument("term")
    retract.add_argument("--pos")
    retract.add_argument("--note", default="")

    override = sub.add_parser("override", help="添加人工校订（按词项与语境生效）")
    override.add_argument("term")
    override.add_argument("pos")
    override.add_argument("--context", required=True, help="校订生效的语境，与文本记录的语境同口径")
    override.add_argument("--teacher", default="")

    revoke = sub.add_parser("revoke-override", help="撤销人工校订")
    revoke.add_argument("override_id")

    sub.add_parser("list-overrides", help="查看人工校订记录")

    reprocess = sub.add_parser("reprocess", help="选择性重处理（保留适用的人工校订）")
    reprocess.add_argument("--record-id", action="append", dest="record_ids")
    reprocess.add_argument("--source")
    reprocess.add_argument("--context")
    reprocess.add_argument("--term")
    reprocess.add_argument("--stale-only", action="store_true")
    reprocess.add_argument("--all", action="store_true", dest="all_records")
    reprocess.add_argument("--dictionary-version", type=int)

    query = sub.add_parser("query", help="句法检索（默认排除已过期标注，可按词典版本复现旧查询）")
    query.add_argument("--pos")
    query.add_argument("--term")
    query.add_argument("--source")
    query.add_argument("--context")
    query.add_argument("--dictionary-version", type=int)
    query.add_argument("--include-stale", action="store_true")
    query.add_argument("--status", choices=("confirmed", "current", "stale", "ambiguous", "unknown"))

    explain = sub.add_parser("explain", help="查看词性判断的词典版本、语境与人工修订来源")
    explain.add_argument("record_id")
    explain.add_argument("--index", type=int)
    explain.add_argument("--token")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    workflow = TextWorkflow(RecordRepository(args.state))
    try:
        if args.action == "ingest":
            result = workflow.ingest(json.loads(Path(args.path).read_text(encoding="utf-8")))
        elif args.action == "list":
            result = workflow.summarize_records(args.source)
        elif args.action == "publish-dict":
            payload = json.loads(Path(args.path).read_text(encoding="utf-8"))
            entries = payload.get("entries") if isinstance(payload, dict) else payload
            result = workflow.publish_dictionary(entries, note=args.note)
        elif args.action == "show-dict":
            result = {"versions": workflow.dictionary_versions(), "entries": workflow.dictionary_entries(args.version)}
        elif args.action == "retract":
            result = workflow.retract_dictionary_entry(args.term, pos=args.pos, note=args.note)
        elif args.action == "override":
            result = workflow.add_override(args.term, args.context, args.pos, teacher=args.teacher)
        elif args.action == "revoke-override":
            result = workflow.revoke_override(args.override_id)
        elif args.action == "list-overrides":
            result = workflow.list_overrides()
        elif args.action == "reprocess":
            result = workflow.reprocess(
                record_ids=args.record_ids,
                source=args.source,
                context=args.context,
                term=args.term,
                stale_only=args.stale_only,
                all_records=args.all_records,
                dictionary_version=args.dictionary_version,
            )
        elif args.action == "query":
            result = workflow.query(
                pos=args.pos,
                term=args.term,
                source=args.source,
                context=args.context,
                dictionary_version=args.dictionary_version,
                include_stale=args.include_stale,
                status=args.status,
            )
        else:
            result = workflow.explain(args.record_id, index=args.index, token=args.token)
    except ValueError as error:
        parser.exit(1, f"错误：{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
