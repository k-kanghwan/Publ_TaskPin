from datetime import datetime

from manager import todo_filter, todo_store

NOW = datetime(2026, 10, 26, 9, 30).astimezone()


def _item(text, item_id=None, parent=None, done=False, snooze=None):
    item = todo_store.new_item(text)
    item["id"] = item_id or text
    item["parent_id"] = parent
    item["done"] = done
    item["snooze_until"] = snooze
    return item


# ==================================================
# 날짜별 보기
# ==================================================
def test_bucket_boundaries():
    assert todo_filter.bucket(_item("a (@2026-10-26 09:29)"), NOW) == "overdue"
    assert todo_filter.bucket(_item("a (@2026-10-26 09:30)"), NOW) == "today"
    assert todo_filter.bucket(_item("a (@2026-10-26 23:59)"), NOW) == "today"
    assert todo_filter.bucket(_item("a (@2026-10-27 00:00)"), NOW) == "upcoming"
    assert todo_filter.bucket(_item("a (@2026-10-20 18:00)"), NOW) == "overdue"


def test_bucket_skips_done_and_no_reminder():
    assert todo_filter.bucket(_item("a (@2026-10-20 18:00)", done=True), NOW) is None
    assert todo_filter.bucket(_item("리마인더 없음"), NOW) is None


def test_bucket_prefers_snooze():
    # 지난 리마인더를 내일로 미뤘으면 예정
    item = _item("a (@2026-10-25 09:00)", snooze="2026-10-27 09:00")
    assert todo_filter.bucket(item, NOW) == "upcoming"


# ==================================================
# 검색
# ==================================================
def test_matches_casefold_and_all_words():
    item = _item("Weekly 회의자료 준비")
    assert todo_filter.matches(item, "weekly")
    assert todo_filter.matches(item, "  준비   회의 ")
    assert not todo_filter.matches(item, "회의 보고서")
    assert todo_filter.matches(item, "")


def test_matches_ignores_reminder_token():
    item = _item("회의 (@2026-10-26 09:00)")
    assert not todo_filter.matches(item, "2026")
    assert todo_filter.matches(item, "회의")


def test_is_active():
    assert not todo_filter.is_active("all", "")
    assert not todo_filter.is_active("all", "   ")
    assert todo_filter.is_active("all", "회의")
    assert todo_filter.is_active("today", "")


# ==================================================
# 보일 항목 / 개수
# ==================================================
def _tree():
    return [
        _item("프로젝트", "p"),
        _item("회의 준비 (@2026-10-26 15:00)", "c1", parent="p"),
        _item("보고서 (@2026-10-25 15:00)", "c2", parent="p"),
        _item("세부 회의록", "g", parent="c2"),
        _item("장보기 (@2026-10-28 18:00)", "s"),
        _item("끝난 회의 (@2026-10-24 10:00)", "d", done=True),
    ]


def test_visible_keeps_ancestors_as_context():
    shown, context = todo_filter.visible(_tree(), "all", "회의록", NOW)
    assert shown == {"g", "c2", "p"}
    assert context == {"c2", "p"}


def test_visible_date_view():
    items = _tree()
    assert todo_filter.visible(items, "today", "", NOW) == ({"c1", "p"}, {"p"})
    assert todo_filter.visible(items, "overdue", "", NOW) == ({"c2", "p"}, {"p"})
    assert todo_filter.visible(items, "upcoming", "", NOW) == ({"s"}, set())


def test_visible_search_includes_done_in_all_view():
    shown, _ = todo_filter.visible(_tree(), "all", "회의", NOW)
    assert {"c1", "g", "d"} <= shown


def test_visible_combines_view_and_query():
    shown, _ = todo_filter.visible(_tree(), "today", "보고서", NOW)
    assert shown == set()


def test_counts():
    items = _tree()
    assert todo_filter.counts(items, "", NOW) == {
        "today": 1,
        "overdue": 1,
        "upcoming": 1,
    }
    assert todo_filter.counts(items, "장보기", NOW) == {
        "today": 0,
        "overdue": 0,
        "upcoming": 1,
    }
