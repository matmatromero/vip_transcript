import re
from pathlib import Path

SECTION_QA_MARKERS = (
    "move on to investor questions",
    "move on to analyst questions",
    "move on to say.com questions",
    "move on to questions",
    "jump into q&a",
    "now we will move on",
    "we will now move on",
    "going to move on to",
)


def _is_role_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) > 100:
        return False
    if re.search(r"\. [a-z]", stripped):
        return False
    lower = stripped.lower()
    sentence_starters = (
        "yes", "no ", "so ", "i ", "we ", "as ", "the ", "and ",
        "but ", "it ", "our ", "for ", "this", "that", "what",
        "actually", "sure", "right", "well", "okay", "in ",
        "thanks", "great", "you", "by ", "with", "if ", "let ",
        "to ", "there", "they", "from", "also", "exactly",
        "i mean", "obviously", "cool", "including",
    )
    if any(lower.startswith(s) for s in sentence_starters):
        return False
    return True


def _detect_section(text: str, current_section: str, has_prior_turns: bool) -> str:
    if current_section == "qa":
        return "qa"
    if not has_prior_turns:
        return current_section
    lower = text.lower()
    if any(marker in lower for marker in SECTION_QA_MARKERS):
        return "qa"
    return current_section


def parse_turns(filepath: str) -> list[dict]:
    raw_lines = Path(filepath).read_text(encoding="utf-8").splitlines()
    lines = [l.strip() for l in raw_lines if l.strip()]

    turns = []
    section = "prepared_remarks"
    i = 0

    while i < len(lines):
        name = lines[i]

        if i + 1 >= len(lines):
            break

        if i + 2 < len(lines) and _is_role_line(lines[i + 1]):
            role = lines[i + 1]
            text = lines[i + 2]
            i += 3
        else:
            role = ""
            text = lines[i + 1]
            i += 2

        section = _detect_section(text, section, has_prior_turns=len(turns) > 0)

        turns.append({
            "turn_index": len(turns),
            "speaker": name,
            "role": role,
            "section": section,
            "text": text,
        })

    return turns
