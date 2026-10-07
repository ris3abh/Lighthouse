"""The one clock. Timestamps are stored as UTC instants; "today" and calendar days are the person's local
days, in the machine's time zone (``TZ`` overrides it).

Use :func:`today` instead of ``date.today()`` and :func:`local_date` instead of ``dt.date()`` on a stored
timestamp: a UTC date is a day ahead in the evening west of Greenwich and a day behind after midnight east of
it. Tests freeze the clock with :func:`freeze`.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo

from tzlocal import get_localzone


def _system_zone() -> tzinfo:
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz:
        try:
            return ZoneInfo(tz)
        except (KeyError, ValueError):
            pass
    return get_localzone()


_instant: Callable[[], datetime] = lambda: datetime.now(UTC)  # noqa: E731
_zone: Callable[[], tzinfo] = _system_zone


def local_tz() -> tzinfo:
    return _zone()


def utcnow() -> datetime:
    """Now, in UTC, to the second (what is stored)."""
    return _instant().astimezone(UTC).replace(microsecond=0)


def now() -> datetime:
    """Now, in the person's time zone."""
    return _instant().astimezone(local_tz())


def today() -> date:
    """The person's calendar day."""
    return now().date()


def local_date(moment: datetime) -> date:
    """The person's calendar day of a stored timestamp (naive timestamps are taken as UTC)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(local_tz()).date()


def end_of_day_utc(day: date) -> datetime:
    """The first instant after the person's ``day`` ends, in UTC (for "as of <day>" cutoffs)."""
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=local_tz()).astimezone(UTC)


def freeze(at: datetime, zone: tzinfo | None = None) -> Callable[[], None]:
    """Pin the clock to ``at`` (aware) and optionally the time zone. Returns a function that undoes it."""
    global _instant, _zone
    saved = (_instant, _zone)
    _instant = lambda: at  # noqa: E731
    if zone is not None:
        _zone = lambda: zone  # noqa: E731

    def undo() -> None:
        global _instant, _zone
        _instant, _zone = saved

    return undo
