"""词典版本管理。

词典按版本发布，版本一旦发布即不可变；撤回词项或义项通过发布一个
去掉对应内容的新版本完成，旧版本保留，供旧查询复现。
"""
import copy

from .text import normalize_context, normalize_text, tokenize

ORIGINS = ("general", "school")


def _normalize_sense(sense, term):
    if not isinstance(sense, dict):
        raise ValueError(f"词条 {term} 的义项格式无效")
    pos = str(sense.get("pos", "")).strip()
    if not pos:
        raise ValueError(f"词条 {term} 存在缺少词性的义项")
    origin = str(sense.get("origin", "general")).strip() or "general"
    if origin not in ORIGINS:
        raise ValueError(f"词条 {term} 的义项来源无效：{origin}")
    contexts = sense.get("contexts", [])
    if not isinstance(contexts, list):
        raise ValueError(f"词条 {term} 的语境列表无效")
    normalized_contexts = sorted({normalize_context(item) for item in contexts if normalize_context(item)})
    return {
        "pos": pos,
        "origin": origin,
        "contexts": normalized_contexts,
        "note": str(sense.get("note", "")).strip(),
    }


def normalize_entries(entries):
    if not isinstance(entries, list):
        raise ValueError("词典内容必须是词条列表")
    normalized = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("词条格式无效")
        term = normalize_text(str(entry.get("term", "")))
        if not term:
            raise ValueError("存在缺少词项的词条")
        if tokenize(term) != [term]:
            raise ValueError(f"词项必须是单个词元：{term}")
        if term in normalized:
            raise ValueError(f"词项重复：{term}")
        senses = entry.get("senses")
        if not isinstance(senses, list) or not senses:
            raise ValueError(f"词条 {term} 缺少词性义项")
        normalized[term] = {"term": term, "senses": [_normalize_sense(sense, term) for sense in senses]}
    return [normalized[term] for term in sorted(normalized)]


def latest_version(dictionary):
    versions = dictionary.get("versions", [])
    return versions[-1] if versions else None


def get_version(dictionary, number):
    for version in dictionary.get("versions", []):
        if version["version"] == number:
            return version
    return None


def publish_version(dictionary, entries, note, published_at):
    normalized = normalize_entries(entries)
    current = latest_version(dictionary)
    number = (current["version"] if current else 0) + 1
    version = {"version": number, "published_at": published_at, "note": note, "entries": normalized}
    dictionary.setdefault("versions", []).append(version)
    return version


def retract_entry(dictionary, term, pos, note, published_at):
    """撤回词项（或指定词性义项）：以去掉该内容的新版本发布，旧版本不动。"""
    current = latest_version(dictionary)
    if current is None:
        raise ValueError("尚未发布词典，无法撤回")
    term = normalize_text(term)
    entries = copy.deepcopy(current["entries"])
    target = next((entry for entry in entries if entry["term"] == term), None)
    if target is None:
        raise ValueError(f"当前词典没有词项：{term}")
    if pos:
        remaining = [sense for sense in target["senses"] if sense["pos"] != pos]
        if len(remaining) == len(target["senses"]):
            raise ValueError(f"词项 {term} 没有词性为 {pos} 的义项")
        if remaining:
            target["senses"] = remaining
        else:
            entries.remove(target)
        default_note = f"撤回词项 {term} 的 {pos} 义项"
    else:
        entries.remove(target)
        default_note = f"撤回词项 {term}"
    return publish_version(dictionary, entries, note or default_note, published_at)


def entries_by_term(version):
    if version is None:
        return {}
    return {entry["term"]: entry for entry in version["entries"]}


def matching_senses(entry, context):
    """按同一语境口径筛选义项：contexts 为空表示适用所有语境。"""
    if entry is None:
        return []
    return [sense for sense in entry["senses"] if not sense["contexts"] or context in sense["contexts"]]


def resolve_senses(senses):
    """校本用法优先于通用义项，语境特定义项优先于通配义项；

    仍有多个词性候选时返回 ambiguous，留待人工校订，不擅自定夺。
    """
    if not senses:
        return "unknown", None, []
    school = [sense for sense in senses if sense["origin"] == "school"]
    pool = school or list(senses)
    specific = [sense for sense in pool if sense["contexts"]]
    if specific:
        pool = specific
    pos_values = sorted({sense["pos"] for sense in pool})
    if len(pos_values) == 1:
        return "unique", pos_values[0], pool
    return "ambiguous", None, pool
