"""人工校订。

校订按（词项, 语境）生效，只追加、不删除：再次校订同一词项与语境时
旧校订被标记为已取代，撤销时标记撤销时间，历史全部保留供溯源。
"""
from .text import normalize_context, normalize_text, tokenize


def is_active(override):
    return not override["revoked_at"] and not override["superseded_by"]


def find_active(overrides, term, context):
    for override in reversed(overrides):
        if override["term"] == term and override["context"] == context and is_active(override):
            return override
    return None


def get_override(overrides, override_id):
    for override in overrides:
        if override["override_id"] == override_id:
            return override
    return None


def add_override(overrides, term, context, pos, teacher, created_at):
    term = normalize_text(term)
    context = normalize_context(context)
    pos = str(pos).strip()
    if not term or tokenize(term) != [term]:
        raise ValueError(f"校订词项必须是单个词元：{term}")
    if not pos:
        raise ValueError("校订缺少词性")
    existing = find_active(overrides, term, context)
    override_id = f"ov-{len(overrides) + 1}"
    if existing is not None:
        existing["superseded_by"] = override_id
    override = {
        "override_id": override_id,
        "term": term,
        "context": context,
        "pos": pos,
        "teacher": str(teacher).strip(),
        "created_at": created_at,
        "revoked_at": None,
        "superseded_by": None,
    }
    overrides.append(override)
    return override


def revoke_override(overrides, override_id, revoked_at):
    override = get_override(overrides, override_id)
    if override is None:
        raise ValueError(f"没有这条人工校订：{override_id}")
    if override["revoked_at"]:
        raise ValueError(f"人工校订已撤销：{override_id}")
    override["revoked_at"] = revoked_at
    return override
