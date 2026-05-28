from datetime import datetime
from slate.jira.scheduler import _seconds_until, parse_sync_time


def test_seconds_until_future_time_is_positive():
    now = datetime.now()
    future_hour = (now.hour + 1) % 24
    seconds = _seconds_until(future_hour, now.minute)
    assert seconds > 0


def test_seconds_until_past_time_schedules_next_day():
    now = datetime.now()
    past_hour = (now.hour - 1) % 24
    seconds = _seconds_until(past_hour, 0)
    assert 22 * 3600 < seconds <= 24 * 3600


def test_seconds_until_returns_float():
    seconds = _seconds_until(9, 0)
    assert isinstance(seconds, float)


def test_parse_sync_time_returns_hour_and_minute():
    hour, minute = parse_sync_time("09:00")
    assert hour == 9
    assert minute == 0


def test_parse_sync_time_evening():
    hour, minute = parse_sync_time("21:30")
    assert hour == 21
    assert minute == 30


def test_parse_sync_time_defaults_to_nine_am_on_invalid():
    hour, minute = parse_sync_time("not-a-time")
    assert hour == 9
    assert minute == 0
