import unittest
from datetime import datetime, timezone

from app.core.time_utils import to_utc_iso


class ToUtcIsoTest(unittest.TestCase):
    """The frontend parses backend-serialized datetimes with new Date(...), which treats a
    string with no timezone offset as LOCAL time. Every datetime in this app is stored as
    naive UTC (datetime.utcnow()), so a bare .isoformat() -- e.g. "2026-08-16T15:59:00" --
    gets misread as 15:59 Beijing time instead of the UTC value it actually is, an 8-hour
    error. to_utc_iso must always emit an explicit UTC offset."""

    def test_none_stays_none(self):
        self.assertIsNone(to_utc_iso(None))

    def test_naive_datetime_gets_utc_offset_appended(self):
        result = to_utc_iso(datetime(2026, 8, 16, 15, 59, 0))
        self.assertEqual(result, "2026-08-16T15:59:00+00:00")

    def test_result_is_unambiguously_parseable_as_utc(self):
        result = to_utc_iso(datetime(2026, 8, 16, 15, 59, 0))
        parsed = datetime.fromisoformat(result)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)
        self.assertEqual(parsed.astimezone(timezone.utc).hour, 15)

    def test_already_aware_datetime_is_left_correct(self):
        aware = datetime(2026, 8, 16, 23, 59, 0, tzinfo=timezone.utc)
        result = to_utc_iso(aware)
        parsed = datetime.fromisoformat(result)
        self.assertEqual(parsed.utcoffset().total_seconds(), 0)


if __name__ == "__main__":
    unittest.main()
