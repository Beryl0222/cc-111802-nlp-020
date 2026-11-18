"""词性标注与过期判定。

每条记录的每次标注生成一个不可变的标注快照（annotation），记录所用
词典版本；每个词性判断都带来源（词典自动 / 人工校订），供事后溯源。
过期判定在查询时对照最新词典与当前人工校订动态计算，不回改快照。
"""
from .dictionary import entries_by_term, get_version, latest_version, matching_senses, resolve_senses
from .overrides import find_active, get_override, is_active
from .text import tokenize

STATUS_ORDER = ("confirmed", "current", "stale", "ambiguous", "unknown")


def judge_token(token, index, context, entries, overrides):
    override = find_active(overrides, token, context)
    if override is not None:
        return {
            "index": index,
            "token": token,
            "pos": override["pos"],
            "basis": "manual",
            "resolution": "confirmed",
            "origin": None,
            "override_id": override["override_id"],
            "candidates": [],
        }
    senses = matching_senses(entries.get(token), context)
    resolution, pos, pool = resolve_senses(senses)
    candidates = []
    if resolution == "ambiguous":
        seen = sorted({(sense["pos"], sense["origin"]) for sense in pool})
        candidates = [{"pos": pos_value, "origin": origin} for pos_value, origin in seen]
    return {
        "index": index,
        "token": token,
        "pos": pos,
        "basis": "dictionary" if resolution == "unique" else "none",
        "resolution": resolution,
        "origin": pool[0]["origin"] if resolution == "unique" else None,
        "override_id": None,
        "candidates": candidates,
    }


def annotate_record(record, dictionary, overrides, dictionary_version, annotated_at, annotation_id):
    context = record["context"]
    entries = entries_by_term(get_version(dictionary, dictionary_version))
    judgments = [
        judge_token(token, index, context, entries, overrides)
        for index, token in enumerate(tokenize(record["text"]))
    ]
    return {
        "annotation_id": annotation_id,
        "dictionary_version": dictionary_version,
        "annotated_at": annotated_at,
        "judgments": judgments,
    }


def evaluate_judgment(judgment, context, dictionary, overrides):
    """对照最新词典与当前人工校订，判断这条标注现在是否仍然有效。

    返回 (status, reason)：confirmed（人工校订仍有效）、current（词典
    自动标注仍与最新版一致）、stale（依据已撤回或失效，不能再当作已
    确认标注）、ambiguous / unknown（当初就未定词性）。
    """
    if judgment["basis"] == "manual":
        override = get_override(overrides, judgment["override_id"])
        if override is None or not is_active(override):
            return "stale", "人工校订已撤销或被新校订取代"
        return "confirmed", ""
    if judgment["resolution"] in ("ambiguous", "unknown"):
        return judgment["resolution"], ""
    version = latest_version(dictionary)
    if version is None:
        return "stale", "词典不可用"
    senses = matching_senses(entries_by_term(version).get(judgment["token"]), context)
    if judgment["pos"] not in {sense["pos"] for sense in senses}:
        return "stale", f"词典第{version['version']}版已不再提供该词性（条目撤回或更改）"
    resolution, pos, _ = resolve_senses(senses)
    if resolution == "unique" and pos == judgment["pos"]:
        return "current", ""
    return "stale", "词典更新后该词项在此语境下的解析已变化"


def select_snapshot(record, dictionary_version=None):
    """选定标注快照：默认取当前快照；指定词典版本时取该版本最近一次

    标注的快照，使按旧版本发起的句法查询可以复现。没有对应快照的
    记录返回 None（该版本下从未标注，不参与此次查询）。
    """
    annotations = record.get("annotations", [])
    if not annotations:
        return None
    if dictionary_version is None:
        current_id = record.get("current_annotation")
        for annotation in annotations:
            if annotation["annotation_id"] == current_id:
                return annotation
        return annotations[-1]
    for annotation in reversed(annotations):
        if annotation["dictionary_version"] == dictionary_version:
            return annotation
    return None
