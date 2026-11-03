from datetime import datetime

from manager import todo_export, todo_store

NOW = datetime(2026, 10, 23, 14, 5)


def _item(text, done=False, parent=None, archived_at=None):
    item = todo_store.new_item(text)
    item["done"] = done
    item["parent_id"] = parent["id"] if parent else None
    if archived_at:
        item["archived_at"] = archived_at
    return item


def _body(markdown):
    """머리말(제목·내보낸 시각·빈 줄) 다음 줄들"""
    return markdown.splitlines()[3:]


def test_markdown_header():
    lines = todo_export.to_markdown([], NOW).splitlines()
    assert lines[0] == "# Task알림 TODO — 현재 페이지"
    assert lines[1] == "내보낸 시각: 2026-10-23 14:05"


def test_markdown_keeps_hierarchy_and_done_state():
    report = _item("보고서 (@2026-10-24 09:00)")
    data = _item("자료 수집", done=True, parent=report)
    draft = _item("초안 🚀", parent=report)
    deep = _item("그림", parent=draft)
    notes = _item("회의록", done=True)

    assert _body(todo_export.to_markdown([report, notes, data, draft, deep], NOW)) == [
        "- [ ] 보고서 (@2026-10-24 09:00)",
        "  - [x] 자료 수집",
        "  - [ ] 초안 🚀",
        "    - [ ] 그림",
        "- [x] 회의록",
    ]


def test_archived_grouped_by_day_with_active_parent():
    active_parent = _item("남은 상위")
    newer = _item("최근", done=True, archived_at="2026-10-23 10:00:00")
    child = _item("하위", done=True, parent=newer, archived_at="2026-10-23 10:00:00")
    orphan = _item(
        "고아", done=True, parent=active_parent, archived_at="2026-10-23 09:00:00"
    )
    older = _item("예전", done=True, archived_at="2026-10-20 18:00:00")

    lines = todo_export.archived_to_markdown(
        [newer, child, orphan, older], NOW, [active_parent]
    )
    assert _body(lines) == [
        "## 2026-10-23 보관",
        "",
        "- [x] 최근",
        "  - [x] 하위",
        "- [ ] 남은 상위",  # 아직 화면 목록에 있는(미완료) 상위도 함께
        "  - [x] 고아",
        "",
        "## 2026-10-20 보관",
        "",
        "- [x] 예전",
    ]


def test_archived_keeps_whole_parent_chain():
    # 사용자 예: 단계C 아래 미완료 "진행 중" 이 남아 있고, 그 아래 d 들만 보관됨
    stage = _item("단계C")
    doing = _item("진행 중", parent=stage)
    d1 = _item("d1", done=True, parent=doing, archived_at="2026-10-23 10:00:00")
    d2 = _item("d2", done=True, parent=doing, archived_at="2026-10-23 10:00:00")
    phase = _item("phase D and F", done=True, archived_at="2026-10-23 10:00:00")

    lines = todo_export.archived_to_markdown([phase, d1, d2], NOW, [stage, doing])
    assert _body(lines) == [
        "## 2026-10-23 보관",
        "",
        "- [x] phase D and F",
        "- [ ] 단계C",
        "  - [ ] 진행 중",
        "    - [x] d1",
        "    - [x] d2",
    ]


def test_archived_parent_from_other_day_repeats_in_each_section():
    parent = _item("상위", done=True, archived_at="2026-10-20 18:00:00")
    child = _item("하위", done=True, parent=parent, archived_at="2026-10-23 10:00:00")

    lines = todo_export.archived_to_markdown([child, parent], NOW)
    assert _body(lines) == [
        "## 2026-10-23 보관",
        "",
        "- [x] 상위",
        "  - [x] 하위",
        "",
        "## 2026-10-20 보관",
        "",
        "- [x] 상위",
    ]


def test_default_filename():
    page, every, archived = todo_export.PAGE, todo_export.ALL, todo_export.ARCHIVED
    assert todo_export.default_filename(page, NOW) == "TaskPin-TODO-20261023.md"
    assert todo_export.default_filename(every, NOW, "Dev") == (
        "TaskPin-TODO-전체-20261023.md"
    )
    assert todo_export.default_filename(archived, NOW) == (
        "TaskPin-TODO-보관-20261023.md"
    )


def test_load_archived_excludes_active(temp_db):
    items = [_item(text, done=True) for text in ("a", "b", "c")]
    todo_store.save_todos(items)
    todo_store.archive_items([items[0]["id"]])

    loaded = todo_store.load_archived()
    assert [item["id"] for item in loaded] == [items[0]["id"]]
    assert loaded[0]["archived_at"]
    assert loaded[0]["done"] is True


def test_markdown_page_name_in_header_and_filename():
    lines = todo_export.to_markdown([], NOW, "Dev").splitlines()
    assert lines[0] == "# Task알림 TODO — Dev · 현재 페이지"
    page = todo_export.PAGE
    assert todo_export.default_filename(page, NOW, "Dev") == (
        "TaskPin-TODO-Dev-20261023.md"
    )
    # 파일 이름에 쓸 수 없는 글자는 _ (보관 항목은 모든 페이지라 이름을 넣지 않는다)
    assert todo_export.default_filename(page, NOW, ' 업무 / 2:3? ') == (
        "TaskPin-TODO-업무 _ 2_3_-20261023.md"
    )
    assert todo_export.default_filename(todo_export.ARCHIVED, NOW, "Dev") == (
        "TaskPin-TODO-보관-20261023.md"
    )
    assert todo_export.default_filename(page, NOW, " .. ") == "TaskPin-TODO-20261023.md"


def test_markdown_separator_and_collapsed_children():
    parent = _item("상위")
    parent["collapsed"] = True  # 접혀 있어도 하위를 쓴다
    child = _item("하위", parent=parent)
    sep = _item("-----")
    last = _item("끝")
    assert _body(todo_export.to_markdown([parent, child, sep, last], NOW)) == [
        "- [ ] 상위",
        "  - [ ] 하위",
        "---",
        "- [ ] 끝",
    ]


def test_to_text_for_clipboard_is_markdown_checklist():
    parent = _item("상위 (@2026-10-24 09:00)")
    child = _item("하위", done=True, parent=parent)
    sep = _item("---")
    assert todo_export.to_text([parent, child, sep]) == (
        "- [ ] 상위 (@2026-10-24 09:00)\n  - [x] 하위\n---"
    )


def _on(page_id, item):
    item["page_id"] = page_id
    return item


def test_all_pages_one_section_per_page_in_order():
    pages = [{"id": 2, "name": "업무"}, {"id": 1, "name": "개인"}, {"id": 3, "name": "빈"}]
    parent = _on(1, _item("장보기"))
    child = _on(1, _item("우유", done=True, parent=parent))
    work = _on(2, _item("보고서 (@2026-10-24 09:00)"))
    lines = todo_export.pages_to_markdown(pages, [parent, child, work], NOW)
    assert lines.splitlines()[0] == "# Task알림 TODO — 전체 페이지"
    assert _body(lines) == [
        "## 업무",
        "",
        "- [ ] 보고서 (@2026-10-24 09:00)",
        "",
        "## 개인",
        "",
        "- [ ] 장보기",
        "  - [x] 우유",
        "",
        "## 빈",  # 할 일이 없는 페이지는 머리줄만
    ]


def test_pending_grouped_by_page_keeps_given_order():
    pages = [{"id": 1, "name": "개인"}, {"id": 2, "name": "업무"}]
    late = _on(2, _item("발표 (@2026-10-25 10:00)"))
    parent = _on(1, _item("상위"))
    early = _on(1, _item("병원 (@2026-10-24 09:00)", parent=parent))
    lines = todo_export.pending_to_markdown(pages, [early, late], NOW)
    assert lines.splitlines()[0] == "# Task알림 TODO — 미완료 · 현재 페이지"
    assert _body(lines) == [
        "## 개인",
        "",
        "- [ ] 병원 (@2026-10-24 09:00)",  # 상위 없이 한 단계
        "",
        "## 업무",
        "",
        "- [ ] 발표 (@2026-10-25 10:00)",
    ]
