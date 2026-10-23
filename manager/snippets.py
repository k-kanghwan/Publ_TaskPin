"""스니펫: 입력 중 `:idea:` 처럼 콜론으로 감싼 트리거를 치면 정해 둔 문구(💡)로 바꾼다.

설정창(Snippets 탭)에서 고친 목록은 config.json 의 "snippets" 에 [[":idea:", "💡"], ...] 로 저장한다.
치환은 TODO 입력/수정칸과 Task 업무명 입력칸에서 한다(ui/text_input.expand_snippet).
"""

import re

DEFAULT_SNIPPETS = [
    [":idea:", "💡"],
    [":rocket:", "🚀"],
    [":check:", "✅"],
    [":fire:", "🔥"],
    [":warn:", "⚠️"],
    [":star:", "⭐"],
    [":memo:", "📝"],
    [":bug:", "🐛"],
]

_NAME_RE = re.compile(r"[^\s:]+")
_TRIGGER_AT_END_RE = re.compile(r":[^\s:]+:$")


def normalize_trigger(name: str):
    """`idea` / `:idea:` -> `:idea:`. 비었거나 공백/콜론이 섞이면 None"""
    name = (name or "").strip()
    if len(name) >= 2 and name.startswith(":") and name.endswith(":"):
        name = name[1:-1]
    return f":{name}:" if _NAME_RE.fullmatch(name) else None


def from_config(cfg: dict) -> dict:
    """설정의 스니펫 목록 -> {트리거: 문구}. 깨진 항목은 건너뛰고, 목록 자체가 없으면 기본값"""
    entries = cfg.get("snippets")
    if not isinstance(entries, list):
        entries = DEFAULT_SNIPPETS
    table = {}
    for entry in entries:
        if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
            continue
        trigger = normalize_trigger(str(entry[0]))
        text = entry[1]
        if trigger and isinstance(text, str) and text and trigger not in table:
            table[trigger] = text
    return table


def expand(text: str, cursor: int, table: dict):
    """커서 바로 앞이 등록된 `:트리거:` 이면 (시작, 끝, 바꿀 문구), 아니면 None"""
    match = _TRIGGER_AT_END_RE.search(text, 0, cursor)
    if match is None or match.group() not in table:
        return None
    return match.start(), match.end(), table[match.group()]
