import re
import unicodedata


TOKEN_RE = re.compile(r"[\u3400-\u9fff]|[A-Za-z]+(?:['’-][A-Za-z]+)*|\d+(?:\.\d+)?|[^\w\s]", re.UNICODE)


def normalize_text(text):
    return " ".join(unicodedata.normalize("NFKC", text).split())


def tokenize(text):
    return TOKEN_RE.findall(normalize_text(text))


def annotate(record):
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
