from datetime import datetime, timedelta

import pytest

from manager import task_clock


def dt(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").astimezone()


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-23 09:37:42", "2026-10-23 09:30:00"),
        ("2026-10-23 09:30:00", "2026-10-23 09:30:00"),
        ("2026-10-23 09:44:59", "2026-10-23 09:30:00"),
        ("2026-10-23 09:45:00", "2026-10-23 09:45:00"),
        ("2026-10-23 00:14:00", "2026-10-23 00:00:00"),
    ],
)
def test_floor_slot(now, expected):
    assert task_clock.floor_slot(dt(now)) == dt(expected)


@pytest.mark.parametrize(
    "now, expected",
    [
        ("2026-10-23 06:36:00", "2026-10-23 06:45:00"),
        ("2026-10-23 06:45:00", "2026-10-23 06:45:00"),
        ("2026-10-23 06:45:20", "2026-10-23 07:00:00"),
        ("2026-10-23 23:50:00", "2026-10-24 00:00:00"),
    ],
)
def test_ceil_slot(now, expected):
    assert task_clock.ceil_slot(dt(now)) == dt(expected)


def test_end_from_duration():
    start = dt("2026-10-23 09:30:00")
    assert task_clock.end_from(start, 90) == dt("2026-10-23 11:00:00")


def test_end_from_crosses_midnight():
    start = dt("2026-10-23 23:30:00")
    assert task_clock.end_from(start, 60) == dt("2026-10-24 00:30:00")


def test_minutes_between():
    assert (
        task_clock.minutes_between(dt("2026-10-23 09:30:00"), dt("2026-10-23 11:00:00"))
        == 90
    )


def test_minutes_between_end_before_start_is_next_day():
    # 같은 날짜로 만든 23:30 -> 00:30 은 다음 날 00:30 으로 본다
    assert (
        task_clock.minutes_between(dt("2026-10-23 23:30:00"), dt("2026-10-23 00:30:00"))
        == 60
    )


def test_duration_and_end_round_trip():
    start = dt("2026-10-23 22:15:00")
    for minutes in range(
        task_clock.STEP_MIN, task_clock.MAX_DURATION_MIN + 1, task_clock.STEP_MIN
    ):
        end = task_clock.end_from(start, minutes)
        assert task_clock.minutes_between(start, end) == minutes


def test_format_duration():
    assert task_clock.format_duration(15) == "0:15"
    assert task_clock.format_duration(60) == "1:00"
    assert task_clock.format_duration(12 * 60) == "12:00"


def test_remaining_display_without_task():
    assert task_clock.remaining_display(None, dt("2026-10-23 09:00:00")) == "--:--"


def test_remaining_display_before_end():
    end = dt("2026-10-23 11:00:00")
    assert task_clock.remaining_display(end, dt("2026-10-23 09:30:00")) == "01:30"
    assert task_clock.remaining_display(end, dt("2026-10-23 10:59:01")) == "00:00"


def test_remaining_display_exactly_at_end():
    end = dt("2026-10-23 11:00:00")
    assert task_clock.remaining_display(end, end) == "00:00"


def test_remaining_display_overtime():
    end = dt("2026-10-23 11:00:00")
    assert task_clock.remaining_display(end, end + timedelta(seconds=1)) == "+00:00"
    assert task_clock.remaining_display(end, dt("2026-10-23 12:15:30")) == "+01:15"


def test_remaining_display_across_midnight():
    end = dt("2026-10-24 00:30:00")
    assert task_clock.remaining_display(end, dt("2026-10-23 23:45:00")) == "00:45"
