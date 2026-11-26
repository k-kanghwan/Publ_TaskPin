from datetime import datetime, timedelta

from manager import todo_export, todo_import, todo_store, todo_tree

NOW = datetime(2026, 11, 26, 18, 22).astimezone()


def _tree(items):
    """[(글자, 레벨, 완료)] - 화면처럼 펼친 순서 (형제 정렬 없이 목록 순서)"""
    return [
        (item["text"], level, item["done"])
        for item, level in todo_tree.flatten(items, hide_collapsed=False)
    ]


def _one(text, **kw):
    pages = todo_import.parse(text, now=NOW, **kw)
    assert len(pages) == 1
    return pages[0]


def test_user_checklist_keeps_hierarchy():
    page = _one("- [ ] 개발 \n  - [ ] 기능1 \n  - [ ] 기능2 \n", fallback_name="내 파일")
    assert page["name"] == "내 파일"
    assert _tree(page["items"]) == [
        ("개발", 0, False),
        ("기능1", 1, False),
        ("기능2", 1, False),
    ]
    parent = page["items"][0]
    assert all(item["parent_id"] == parent["id"] for item in page["items"][1:])
    assert all(item["page_id"] is None for item in page["items"])


def test_exported_page_round_trip():
    def item(text, done=False, parent=None):
        new = todo_store.new_item(text)
        new["done"] = done
        new["parent_id"] = parent["id"] if parent else None
        return new

    report = item("보고서 (@2026-12-01 09:00)")
    data = item("자료 수집", done=True, parent=report)
    deep = item("깊은 하위", done=True, parent=data)
    line = item("---", parent=report)
    other = item("다른 일")
    items = [report, data, deep, line, other]
    markdown = todo_export.to_markdown(items, NOW, "🧪 Task·위젯")

    page = _one(markdown, fallback_name="파일 이름")
    assert page["name"] == "🧪 Task·위젯"  # 제목에서
    assert _tree(page["items"]) == _tree(items)
    assert todo_export.to_markdown(page["items"], NOW, page["name"]) == markdown


def test_exported_all_pages_split_into_sections():
    first, second = todo_store.new_item("첫 페이지 일", 1), todo_store.new_item("둘째", 2)
    pages = [{"id": 1, "name": "업무"}, {"id": 2, "name": "개인"}, {"id": 3, "name": "빈"}]
    markdown = todo_export.pages_to_markdown(pages, [first, second], NOW)

    result = todo_import.parse(markdown, todo_import.SECTIONS, "전체", now=NOW)
    assert [(p["name"], [i["text"] for i in p["items"]]) for p in result] == [
        ("업무", ["첫 페이지 일"]),
        ("개인", ["둘째"]),
    ]  # 빈 섹션은 뺀다
    single = _one(markdown, fallback_name="전체")
    assert single["name"] == "전체"  # "— 전체 페이지" 제목은 이름 후보가 아님
    assert [i["text"] for i in single["items"]] == ["첫 페이지 일", "둘째"]


def test_sections_items_before_first_heading_go_to_first_page():
    text = "# 계획\n- [ ] 앞\n## 섹션\n- [ ] 뒤\n"
    result = todo_import.parse(text, todo_import.SECTIONS, now=NOW)
    assert [(p["name"], len(p["items"])) for p in result] == [("계획", 1), ("섹션", 1)]


def test_indent_width_does_not_matter():
    for unit in ("  ", "    ", "\t"):
        text = f"- [ ] 위\n{unit}- [ ] 아래\n{unit}{unit}- [ ] 더 아래\n- [ ] 다음"
        page = _one(text)
        assert [lvl for _, lvl, _ in _tree(page["items"])] == [0, 1, 2, 0], repr(unit)


def test_uneven_indent_uses_nearest_shallower_parent():
    text = "- a\n     - b\n   - c\n - d\n- e"
    levels = {t: lvl for t, lvl, _ in _tree(_one(text)["items"])}
    assert levels == {"a": 0, "b": 1, "c": 1, "d": 1, "e": 0}


def test_separator_has_no_children():
    text = "- [ ] 위\n  ---\n  - [ ] 아래\n***\n- [ ] 끝"
    page = _one(text)
    assert _tree(page["items"]) == [
        ("위", 0, False),
        ("---", 1, False),
        ("아래", 1, False),
        ("---", 0, False),
        ("끝", 0, False),
    ]


def test_skips_non_list_lines():
    text = "\n".join(
        [
            "---",
            "tags: [a]",
            "---",
            "# 제목",
            "내보낸 시각: 2026-11-26 18:22",
            "그냥 글자 줄",
            "### 작은 제목",
            "- [ ] ",
            "- [ ] 할 일",
            "  이어지는 글자 줄",
            "* 별표",
            "+ 더하기",
            "1. 번호",
            "2) 괄호 번호",
            "#태그는 제목이 아님",
        ]
    )
    page = _one(text)
    assert page["name"] == "제목"
    assert [i["text"] for i in page["items"]] == ["할 일", "별표", "더하기", "번호", "괄호 번호"]


def test_front_matter_without_end_is_a_separator():
    page = _one("---\n- [ ] 일")
    assert [i["text"] for i in page["items"]] == ["---", "일"]


def test_no_items_gives_no_pages():
    assert todo_import.parse("# 제목\n글자만\n---\n", now=NOW) == []


def test_done_marks_and_done_rule():
    text = "- [x] 완료 상위\n  - [ ] 미완료 하위\n  ---\n- [X] 대문자\n  - [x] 하위\n  ---\n- [-] 취소"
    page = _one(text)
    assert _tree(page["items"]) == [
        ("완료 상위", 0, False),  # 미완료 하위가 있으면 상위도 미완료
        ("미완료 하위", 1, False),
        ("---", 1, False),
        ("대문자", 0, True),
        ("하위", 1, True),
        ("---", 1, True),  # 구분선은 상위를 따른다
        ("취소", 0, False),
    ]


def test_past_reminder_is_marked_fired():
    past = todo_store.format_token(NOW - timedelta(hours=1))
    later = todo_store.format_token(NOW + timedelta(hours=1))
    page = _one(f"- [ ] 지난 {past}\n- [ ] 나중 {later}\n- [x] 한 일 {past}")
    passed, coming, done = page["items"]
    assert passed["fired"] == todo_store.due_key(todo_store.due_at(passed))
    assert not todo_store.is_due(passed, NOW)
    assert coming["fired"] is None and done["fired"] is None


def test_long_page_name_is_cut():
    page = _one("# " + "가" * 40 + "\n- 일")
    assert page["name"] == "가" * 20


def test_page_name_from_file():
    assert todo_import.page_name_from_file(r"C:\a\TaskPin-TODO-🧪 Task·위젯-20261126.md") == "🧪 Task·위젯"
    assert todo_import.page_name_from_file("TaskPin-TODO-20261126.md") == ""
    assert todo_import.page_name_from_file("/x/내 할 일.md") == "내 할 일"


def test_read_file_encodings(tmp_path):
    utf8 = tmp_path / "utf8.md"
    utf8.write_bytes("\ufeff- [ ] 한글".encode("utf-8"))
    assert todo_import.read_file(str(utf8)) == "- [ ] 한글"
    ansi = tmp_path / "ansi.md"
    ansi.write_bytes("- [ ] 메모장".encode("cp949"))
    assert todo_import.read_file(str(ansi)) == "- [ ] 메모장"
