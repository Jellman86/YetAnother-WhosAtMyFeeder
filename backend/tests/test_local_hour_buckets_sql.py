"""The aligned hour bucket SQL, run on SQLite's own date functions."""

import sqlite3

from app.utils.local_hour_buckets import utc_hour_bucket_sql


def _bucket(stamp: str, alignment: int) -> str:
    with sqlite3.connect(":memory:") as db:
        return db.execute(f"SELECT {utc_hour_bucket_sql('?', alignment)}", (stamp,)).fetchone()[0]


def test_the_bucket_sql_keeps_whole_hours_as_they_were():
    assert _bucket("2026-11-25 18:40:12.5", 0) == "2026-11-25T18:00:00Z"


def test_the_bucket_sql_starts_kolkata_hours_at_half_past():
    # 18:40 UTC is 00:10 on the 26th in Kolkata, in the local hour that began at 18:30 UTC.
    assert _bucket("2026-11-25 18:40:12.5", 30) == "2026-11-25T18:30:00Z"
    # 18:20 UTC is 23:50 on the 25th, in the hour that began at 17:30 UTC.
    assert _bucket("2026-11-25 18:20:00", 30) == "2026-11-25T17:30:00Z"
