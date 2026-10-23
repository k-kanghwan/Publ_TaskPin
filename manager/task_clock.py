"""Task 시간 계산 (Qt 없는 순수 함수)

  - 시작/종료는 15분 단위
  - 소요시간과 종료시간은 서로 계산된다 (종료 = 시작 + 소요)
  - 남은시간이 0 을 지나면 초과 시간을 `+HH:MM` 으로 표시한다
"""

from datetime import datetime, timedelta


STEP_MIN = 15
MAX_DURATION_MIN = 12 * 60
DEFAULT_DURATION_MIN = 60
EMPTY_TIME = "--:--"


def floor_slot(dt: datetime) -> datetime:
    """15분 단위로 내림 (09:37 -> 09:30)"""
    return dt.replace(minute=dt.minute - dt.minute % STEP_MIN, second=0, microsecond=0)


def end_from(start: datetime, minutes: int) -> datetime:
    return start + timedelta(minutes=minutes)


def minutes_between(start: datetime, end: datetime) -> int:
    """시작 -> 종료 분. 종료가 시작 이전(같아도)이면 다음 날 시각으로 본다."""
    minutes = int((end - start).total_seconds() // 60)
    while minutes <= 0:
        minutes += 24 * 60
    return minutes


def format_duration(minutes: int) -> str:
    """소요시간 표시 (75 -> "1:15")"""
    h, m = divmod(minutes, 60)
    return f"{h}:{m:02}"


def remaining_seconds(end: datetime, now: datetime) -> int:
    """양수: 남은 초 / 음수: 초과한 초"""
    return int((end - now).total_seconds())


def remaining_display(end, now: datetime) -> str:
    """위젯 표시용 남은시간. 남았으면 HH:MM, 지났으면 +HH:MM, Task 가 없으면 --:--"""
    if end is None:
        return EMPTY_TIME
    sec = remaining_seconds(end, now)
    sign = "" if sec >= 0 else "+"
    h, m = divmod(abs(sec) // 60, 60)
    return f"{sign}{h:02}:{m:02}"
