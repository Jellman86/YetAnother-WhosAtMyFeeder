from sqlalchemy import Table, Column, Integer, String, Float, Boolean, TIMESTAMP, MetaData, Index
from sqlalchemy.sql import func

metadata = MetaData()

detections = Table(
    "detections",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("detection_time", TIMESTAMP, nullable=False),
    Column("detection_index", Integer, nullable=False),
    Column("score", Float, nullable=False),
    Column("display_name", String, nullable=False),
    Column("category_name", String, nullable=False),
    Column("frigate_event", String, unique=True, nullable=False),
    Column("camera_name", String, nullable=False),
    Column("is_hidden", Boolean, server_default="0"),
    Column("frigate_score", Float),
    Column("sub_label", String),
    Column("audio_confirmed", Boolean, server_default="0"),
    Column("audio_species", String),
    Column("audio_score", Float),
    Column("temperature", Float),
    Column("weather_condition", String),
    Column("scientific_name", String),
    Column("common_name", String),
    Column("taxa_id", Integer),
    # Video classification columns
    Column("video_classification_score", Float),
    Column("video_classification_label", String),
    Column("video_classification_index", Integer),
    Column("video_classification_timestamp", TIMESTAMP),
    Column("video_classification_status", String),
)

# Indices for detections
Index("idx_detections_time", detections.c.detection_time)
Index("idx_detections_species", detections.c.display_name)
Index("idx_detections_hidden", detections.c.is_hidden)
Index("idx_detections_camera", detections.c.camera_name)
Index("idx_detections_scientific", detections.c.scientific_name)
Index("idx_detections_common", detections.c.common_name)
Index("idx_detections_taxa_id", detections.c.taxa_id)
Index("idx_detections_frigate_event", detections.c.frigate_event)
Index("idx_detections_video_status", detections.c.video_classification_status)

taxonomy_cache = Table(
    "taxonomy_cache",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scientific_name", String, nullable=False, unique=True),
    Column("common_name", String),
    Column("taxa_id", Integer),
    Column("is_not_found", Boolean, server_default="0"),
    Column("last_updated", TIMESTAMP, server_default=func.now()),
)

# Indices for taxonomy_cache
Index("idx_taxonomy_scientific", taxonomy_cache.c.scientific_name)
Index("idx_taxonomy_common", taxonomy_cache.c.common_name)
