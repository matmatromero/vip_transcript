import re


def split_into_sentences(text: str) -> list[str]:
    text = re.sub(r"[\r\n]+", " ", text).strip()
    pattern = r'(?<=[.!?])\s+(?=[A-Z\["\'])'
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p.strip()]
