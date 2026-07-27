import re
import time
import uuid


def new_id() -> str:
    return uuid.uuid4().hex[:16]


def now_ts() -> int:
    return int(time.time() * 1000)


_JALALI_INPUT_RE = re.compile(r"^(\d{3,4})[/\-](\d{1,2})[/\-](\d{1,2})$")

# Days in each Jalali month for a non-leap year — good enough for format/range validation
# without pulling in a full calendar-conversion dependency. Esfand (12th month) can have 29
# or 30 days depending on leap year; we allow 30 here rather than reject valid leap dates,
# accepting the small tradeoff of also allowing a handful of invalid Feb-29-equivalent dates
# through (same posture as many lightweight Jalali validators — not a security boundary).
_MONTH_DAYS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 30]


def normalize_jalali(raw: str) -> str | None:
    """Validates & zero-pads a Jalali date string to 'YYYY/MM/DD', or returns None if invalid.
    Mirrors normalizeJalali() in the frontend (format + range check; not a full calendar
    round-trip, see _MONTH_DAYS note above)."""
    if not raw:
        return None
    m = _JALALI_INPUT_RE.match(raw.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if mo < 1 or mo > 12 or d < 1:
        return None
    if d > _MONTH_DAYS[mo - 1]:
        return None
    return f"{y:04d}/{mo:02d}/{d:02d}"


def parse_json_list_or_none(raw):
    import json

    if raw is None:
        return None
    return json.loads(raw)
