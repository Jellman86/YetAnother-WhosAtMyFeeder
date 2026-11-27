"""Record which BirdNET-Go source each stored call came from, by the id a rename leaves alone.

Audio history grouped calls by the source's name, so renaming a source in BirdNET-Go split it in
two (#1111). BirdNET-Go also reports an id for each source, derived from a hash of its stream URL
or sound-card device, and the node that heard it. Both were already kept in each row's payload;
this copies them into columns, with the name the source was given on that call, so Audio history
can group and filter its sources by them.

``source_resolved`` records that a call's source has been read. A call stored by a release from
before this one, run against this schema after a rollback, keeps its default of 0, and YA-WAMF
reads it at its next start (``app/services/audio/source_backfill.py``), found through a partial
index that holds only those calls.

Additive and nullable. A row whose payload carries no id keeps a NULL id and is grouped by its
name, as before. A payload that cannot be read, or a value that is not safe to keep, leaves its
column NULL rather than stopping the upgrade. Downgrade drops the columns: everything in them is
still in the payload.

Like every revision, this runs while YA-WAMF starts, before anything else writes, inside one
transaction. Batches bound how many rows are held in memory, not how long the write lock is held:
about two seconds for 58,000 calls.

Revision ID: d4b8f2a6c1e3
Revises: f3a9c1d27b40
"""

import json
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "d4b8f2a6c1e3"
down_revision = "f3a9c1d27b40"
branch_labels = None
depends_on = None

TABLE = "audio_detections"
INDEX = "idx_audio_detections_source_identity"
PENDING_INDEX = "idx_audio_detections_source_pending"
COLUMNS = ("source_node", "source_id", "source_name")
RESOLVED = "source_resolved"
BATCH_SIZE = 1_000


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(TABLE)}


# Every value below came from an untrusted MQTT message. Identifiers are refused rather than cut
# short, so two distinct ids never become one; names lose control characters. These are copies of
# app/utils/audio_source_identity.py, so later code changes cannot alter what this revision wrote.
MAX_TEXT = 200
UNSAFE = frozenset({"Cc", "Cs"})


def _node(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_TEXT:
        return None
    if any(unicodedata.category(character) in UNSAFE for character in cleaned):
        return None
    return cleaned


def _identifier(value: object) -> str | None:
    # An id also never holds a mapping separator, a wildcard or a space.
    cleaned = _node(value)
    return None if cleaned is None or re.search(r"[,;|*\s]", cleaned) else cleaned


def _label(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > MAX_TEXT * 4:
        return None
    visible = "".join(
        " " if unicodedata.category(character) == "Cc" else character
        for character in value
        if unicodedata.category(character) != "Cs"
    )
    cleaned = " ".join(visible.split())
    return cleaned if cleaned and len(cleaned) <= MAX_TEXT else None


def _first_text(*values: object) -> object:
    return next((value for value in values if isinstance(value, str) and value.strip()), None)


def _source(sensor_id: object, raw_data: object) -> tuple[str | None, str | None, str | None]:
    """(node, source id, name) as ingest records them; an unreadable payload names none."""
    try:
        payload = json.loads(raw_data) if isinstance(raw_data, str) else None
    except (TypeError, ValueError, RecursionError):
        payload = None
    if not isinstance(payload, dict):
        return None, None, _label(sensor_id)
    nested = payload.get("Source")
    nested = nested if isinstance(nested, dict) else {}
    node = _node(payload.get("SourceNode"))
    id_fields = (payload.get("sourceId"), nested.get("id"), payload.get("src"))
    source_id = _identifier(_first_text(*id_fields))
    if source_id is None and any(
        value is not None and not (isinstance(value, str) and not value.strip()) for value in id_fields
    ):
        # The call sent an id that is refused: it keeps its install, and no name to join a source by.
        return node, None, None
    # A name BirdNET-Go sent counts even when it equals the id; a label made from the id does not.
    name_field = _first_text(payload.get("nm"), payload.get("sourceName"), nested.get("displayName"))
    if name_field is not None:
        name = _label(name_field)
    else:
        ids = {
            value.strip()
            for value in (payload.get("sourceId"), payload.get("src"), nested.get("id"))
            if isinstance(value, str) and value.strip()
        }
        sensor = sensor_id.strip() if isinstance(sensor_id, str) else ""
        name = _label(sensor) if sensor and sensor not in ids else None
    return node, source_id, name


def upgrade() -> None:
    existing = _columns()
    for column in COLUMNS:
        if column not in existing:
            op.add_column(TABLE, sa.Column(column, sa.String(), nullable=True))
    if RESOLVED not in existing:
        op.add_column(TABLE, sa.Column(RESOLVED, sa.Boolean(), nullable=False, server_default=sa.text("0")))
    # Only the calls whose source is still to be read: empty once every call has been read.
    op.execute(f"CREATE INDEX IF NOT EXISTS {PENDING_INDEX} ON {TABLE} (id) WHERE {RESOLVED} = 0")

    bind = op.get_bind()
    while True:
        rows = bind.execute(
            sa.text(
                f"SELECT id, sensor_id, raw_data FROM audio_detections WHERE {RESOLVED} = 0 ORDER BY id LIMIT :limit"
            ),
            {"limit": BATCH_SIZE},
        ).fetchall()
        if not rows:
            break
        bind.execute(
            sa.text(
                "UPDATE audio_detections SET source_node = :node, source_id = :source_id,"
                f" source_name = :name, {RESOLVED} = 1 WHERE id = :id"
            ),
            [
                {"id": int(row_id), "node": node, "source_id": source_id, "name": name}
                for row_id, sensor_id, raw_data in rows
                for node, source_id, name in [_source(sensor_id, raw_data)]
            ],
        )

    # Source lists read each (node, id, name) with its newest time from this index alone. It
    # leads with the source, not visibility, so time-window reads keep the timestamp index.
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON {TABLE} (source_node, source_id, source_name, is_hidden, timestamp)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {PENDING_INDEX}")
    existing = _columns()
    for column in (RESOLVED, *reversed(COLUMNS)):
        if column in existing:
            op.drop_column(TABLE, column)
