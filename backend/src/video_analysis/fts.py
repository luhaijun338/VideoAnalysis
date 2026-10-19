import jieba


def tokenize_fts(*parts: str) -> str:
    tokens: list[str] = []
    for part in parts:
        for token in jieba.cut(part):
            stripped = token.strip()
            if stripped:
                tokens.append(stripped)
    return " ".join(tokens)
