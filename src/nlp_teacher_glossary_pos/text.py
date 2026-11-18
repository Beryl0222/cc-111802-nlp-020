import re
import unicodedata


TOKEN_RE = re.compile(r"[\u3400-\u9fff]|[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:\.\d+)?|[^\w\s]", re.UNICODE)



def normalize_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def normalize_context(context):
    """语境口径：词典义项、人工校订、文本记录与句法查询共用同一规范化。"""
    return normalize_text(str(context or ""))


def tokenize(text):
    return TOKEN_RE.findall(normalize_text(text))


def analyze(record):
    tokens = tokenize(record["text"])
    unique = []
    for token in tokens:
        if token not in unique:
            unique.append(token)
    return {
        "tokens": tokens,
        "terms": unique,
        "character_count": len(normalize_text(record["text"])),
        "token_count": len(tokens),
    }
