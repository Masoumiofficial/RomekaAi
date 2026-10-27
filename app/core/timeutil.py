"""Timezone boundary. The planning engine only knows minutes-from-midnight;
conversion to/from wall-clock time happens HERE, at the API boundary."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone(name: str | None):
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return timezone.utc


def today_in(name: str | None) -> date:
    """'Today' means today for the USER, not for the server."""
    return datetime.now(zone(name)).date()


def local_minute_to_utc(day: date, minute: int, name: str | None) -> datetime:
    """Store a naive-UTC datetime (SQLite drops tzinfo) for a local wall-clock minute."""
    local = datetime.combine(day, time.min, tzinfo=zone(name))
    return (local + timedelta(minutes=minute)).astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local_minute(value: datetime | None, day: date, name: str | None) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:                 # SQLite returns naive datetimes
        value = value.replace(tzinfo=timezone.utc)
    local = value.astimezone(zone(name))
    return local.hour * 60 + local.minute if local.date() == day else None
