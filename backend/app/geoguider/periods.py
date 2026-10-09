"""Turn phrases such as 'past 10 years' or 'between March 2019 and June 2021' into exact dates, relative to a given 'today'."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20}
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = r"(\d{1,3}|" + "|".join(NUMBER_WORDS) + r")"
_REL = re.compile(r"\b(?:past|last|previous|preceding)\s+(?:" + _NUM + r"\s+)?(year|yr|month|week|day|decade)s?\b", re.I)
_SINCE = re.compile(r"\bsince\s+(?:(" + MONTH_RE + r")\w*\s+)?((?:19|20)\d{2})\b", re.I)
_POINT = r"(?:(?:" + MONTH_RE + r")\w*\s+(?:19|20)\d{2}|(?:19|20)\d{2}-\d{2}-\d{2}|(?:19|20)\d{2})"
_RANGE = re.compile(r"\b(?:between|from)\s+(" + _POINT + r")\s+(?:and|to|until|through|-)\s+(" + _POINT + r")", re.I)
_IN_YEAR = re.compile(r"\b(?:in|during|for)\s+((?:19|20)\d{2})\b", re.I)


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    span: tuple[int, int]  # character span of the phrase in the original text (stripped before place extraction)


def sub_months(d: date, n: int) -> date:
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _point(s: str, end: bool) -> date | None:
    s = s.strip().lower()
    try:
        m = re.fullmatch(r"((?:19|20)\d{2})-(\d{2})-(\d{2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"([a-z]+)\s+((?:19|20)\d{2})", s)
        if m:
            mon = MONTHS.get(m.group(1)) or MONTHS.get(m.group(1)[:3])
            if mon:
                y = int(m.group(2))
                return date(y, mon, calendar.monthrange(y, mon)[1] if end else 1)
            return None
        m = re.fullmatch(r"((?:19|20)\d{2})", s)
        if m:
            y = int(m.group(1))
            return date(y, 12, 31) if end else date(y, 1, 1)
    except ValueError:
        return None
    return None


def resolve_period(text: str, today: date) -> Period | None:
    """First recognisable period phrase in ``text``; the end is never after ``today``. None when there is no period."""
    m = _RANGE.search(text)
    if m:
        a, b = _point(m.group(1), False), _point(m.group(2), True)
        if a and b:
            b = min(b, today)
            if a <= b:
                return Period(a, b, f"{a:%d %b %Y} to {b:%d %b %Y}", m.span())
    m = _REL.search(text)
    if m:
        raw, unit = (m.group(1) or "1").lower(), m.group(2).lower()
        n = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 1)
        if 0 < n <= 100:
            if unit == "decade":
                start, label = sub_months(today, 120 * n), f"the past {n} decade{'s' if n != 1 else ''}"
            elif unit in ("year", "yr"):
                start, label = sub_months(today, 12 * n), f"the past {n} year{'s' if n != 1 else ''}"
            elif unit == "month":
                start, label = sub_months(today, n), f"the past {n} month{'s' if n != 1 else ''}"
            else:
                days = n * (7 if unit == "week" else 1)
                start, label = today - timedelta(days=days), f"the past {n} {unit}{'s' if n != 1 else ''}"
            return Period(start, today, label, m.span())
    m = _SINCE.search(text)
    if m:
        mon = (MONTHS.get(m.group(1).lower()) or MONTHS.get(m.group(1).lower()[:3], 1)) if m.group(1) else 1
        try:
            start = date(int(m.group(2)), mon, 1)
        except ValueError:
            return None
        if start <= today:
            return Period(start, today, f"since {start:%b %Y}", m.span())
    m = _IN_YEAR.search(text)
    if m:
        y = int(m.group(1))
        if y <= today.year:
            return Period(date(y, 1, 1), min(date(y, 12, 31), today), f"the year {y}", m.span())
    return None
