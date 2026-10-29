import json

from manager import os_win, paths, snippets, widget_config

TABLE = {":idea:": "💡", ":rocket:": "🚀"}


# ==================================================
# 스니펫
# ==================================================
def test_normalize_trigger():
    assert snippets.normalize_trigger("idea") == ":idea:"
    assert snippets.normalize_trigger(" :idea: ") == ":idea:"
    assert snippets.normalize_trigger("할일") == ":할일:"
    for bad in ("", "  ", "::", "a b", "a:b", ":"):
        assert snippets.normalize_trigger(bad) is None


def test_expand_at_cursor():
    text = "회의 :idea:"
    assert snippets.expand(text, len(text), TABLE) == (3, len(text), "💡")


def test_expand_only_right_before_cursor():
    text = ":idea: 정리"
    assert snippets.expand(text, len(text), TABLE) is None
    assert snippets.expand(text, 6, TABLE) == (0, 6, "💡")  # 커서가 트리거 바로 뒤


def test_expand_ignores_unknown_and_time_like_text():
    assert snippets.expand(":nope:", 6, TABLE) is None
    assert snippets.expand("10:30:", 6, TABLE) is None
    assert snippets.expand("idea:", 5, TABLE) is None


def test_expand_after_colon_and_emoji():
    text = "시간 10:30🚀:rocket:"
    start, end, replacement = snippets.expand(text, len(text), TABLE)
    assert text[start:end] == ":rocket:" and replacement == "🚀"


def test_from_config_filters_broken_entries():
    cfg = {
        "snippets": [
            [":idea:", "💡"],
            ["memo", "📝"],  # 콜론 없이 저장돼도 받아준다
            [":idea:", "중복"],  # 먼저 나온 것이 이긴다
            ["a b", "x"],
            [":empty:", ""],
            "깨진 값",
            [":n:", 1],
        ]
    }
    assert snippets.from_config(cfg) == {":idea:": "💡", ":memo:": "📝"}


def test_from_config_defaults_when_missing():
    assert snippets.from_config({}) == dict(snippets.DEFAULT_SNIPPETS)
    assert snippets.from_config({"snippets": []}) == {}  # 사용자가 모두 지운 경우


# ==================================================
# 설정 (단축키 / 기본값)
# ==================================================
def test_shortcuts_fill_missing_and_broken():
    cfg = {
        "shortcuts": {"task_register": "F2", "task_clear": None, "todo_focus": ""},
    }
    assert widget_config.shortcuts(cfg) == {
        "task_register": "F2",
        "task_edit": "R",
        "task_clear": "C",
        "todo_focus": "",  # 빈 문자열은 해제
        "todo_edit": "Return",
        "todo_delete": "Del",
        "todo_cut": "Ctrl+X",
        "todo_copy": "Ctrl+C",
        "todo_paste": "Ctrl+V",
        "todo_check": "Space",
        "todo_outdent": "<",
        "todo_indent": ">",
        "todo_up": "Up",
        "todo_down": "Down",
        "todo_collapse": "Left",
        "todo_expand": "Right",
        "todo_first": "G, G",
        "todo_last": "Shift+G",
        "todo_search": "Ctrl+F",
        "todo_page_prev": "Ctrl+PgUp",
        "todo_page_next": "Ctrl+PgDown",
        "settings": "Ctrl+,",
    }
    assert widget_config.shortcuts({"shortcuts": "깨짐"}) == (
        widget_config.DEFAULT_SHORTCUTS
    )


def test_new_shortcut_default_yields_to_user_key():
    # v0.1.9 에 생긴 task_edit(R) 를 사용자가 이미 다른 동작에 쓰고 있으면 비워 둔다
    cfg = {"shortcuts": {"todo_focus": "R"}}
    result = widget_config.shortcuts(cfg)
    assert result["todo_focus"] == "R"
    assert result["task_edit"] == ""


def test_todo_search_default_yields_to_user_key():
    # 할 일 검색(Ctrl+F) 도 사용자가 이미 다른 동작에 쓰는 키면 비워 둔다
    result = widget_config.shortcuts({"shortcuts": {"settings": "Ctrl+F"}})
    assert result["settings"] == "Ctrl+F"
    assert result["todo_search"] == ""


def test_todo_edit_default_is_enter_unless_taken():
    # 할 일 수정: v0.1.22 부터 기본 Enter (F2 는 고정 키 - ClockWidget.apply_shortcuts)
    assert widget_config.shortcuts({"shortcuts": {}})["todo_edit"] == "Return"
    result = widget_config.shortcuts({"shortcuts": {"task_edit": "Return"}})
    assert result["task_edit"] == "Return"
    assert result["todo_edit"] == ""
    # 이미 저장한 값은 그대로 둔다
    saved = widget_config.shortcuts({"shortcuts": {"todo_edit": "F2"}})
    assert saved["todo_edit"] == "F2"


def test_edit_list_keys_default_unless_taken():
    # v0.1.22 에 생긴 삭제 / 잘라내기 / 복사 / 붙여넣기 (목록 키)
    result = widget_config.shortcuts({"shortcuts": {}})
    assert [result[a] for a in ("todo_delete", "todo_cut", "todo_copy", "todo_paste")] == [
        "Del",
        "Ctrl+X",
        "Ctrl+C",
        "Ctrl+V",
    ]
    assert set(widget_config.LIST_SHORTCUTS) >= {"todo_delete", "todo_paste"}
    result = widget_config.shortcuts({"shortcuts": {"todo_search": "Ctrl+C"}})
    assert result["todo_search"] == "Ctrl+C"
    assert result["todo_copy"] == ""


def test_load_config_does_not_share_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "data_path", lambda name: str(tmp_path / name))
    cfg = widget_config.load_config()
    cfg["shortcuts"]["task_register"] = "X"
    cfg["snippets"].append([":x:", "x"])
    assert widget_config.DEFAULT_SHORTCUTS["task_register"] == "E"
    assert [":x:", "x"] not in snippets.DEFAULT_SNIPPETS

    widget_config.save_config(cfg)
    saved = json.loads((tmp_path / widget_config.CONFIG_NAME).read_text("utf-8"))
    assert saved["shortcuts"]["task_register"] == "X"
    assert widget_config.load_config()["snippets"][-1] == [":x:", "x"]


# ==================================================
# 이모지 패널 문자 메시지 (서로게이트 쌍 합치기)
# ==================================================
def _feed_all(decoder, message, text):
    data = text.encode("utf-16-le")
    units = [int.from_bytes(data[i : i + 2], "little") for i in range(0, len(data), 2)]
    return [decoder.feed(message, unit) for unit in units]


def test_ime_char_joins_surrogate_pair():
    results = _feed_all(os_win.ImeCharDecoder(), os_win.WM_IME_CHAR, "🚀")
    assert results == [(True, None), (True, "🚀")]


def test_ime_char_keeps_zwj_sequence_order():
    text = "👨‍👩‍👧"
    results = _feed_all(os_win.ImeCharDecoder(), os_win.WM_IME_CHAR, text)
    assert all(swallow for swallow, _ in results)
    assert "".join(t for _, t in results if t) == text


def test_wm_char_passes_bmp_to_qt():
    decoder = os_win.ImeCharDecoder()
    assert decoder.feed(os_win.WM_CHAR, ord("e")) == (False, None)
    assert _feed_all(decoder, os_win.WM_CHAR, "🚀")[-1] == (True, "🚀")


def test_lone_low_surrogate_is_dropped():
    decoder = os_win.ImeCharDecoder()
    assert decoder.feed(os_win.WM_IME_CHAR, 0xDE80) == (True, None)
    assert decoder.feed(os_win.WM_IME_CHAR, ord("가")) == (True, "가")


def test_list_shortcuts_yield_to_user_key():
    # 목록 키(위 / 아래 / 접기 / 펼치기)도 설정 단축키 - 사용자가 이미 쓰는 키면 기본값을 비운다
    result = widget_config.shortcuts({"shortcuts": {"todo_edit": "Up"}})
    assert result["todo_up"] == ""
    assert result["todo_down"] == "Down"
    assert set(widget_config.LIST_SHORTCUTS) <= set(widget_config.DEFAULT_SHORTCUTS)
