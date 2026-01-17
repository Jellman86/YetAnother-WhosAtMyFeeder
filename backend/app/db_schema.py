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
    # AI naturalist analysis
    Column("ai_analysis", String),
    Column("ai_analysis_timestamp", TIMESTAMP),
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

oauth_tokens = Table(
    "oauth_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("provider", String, nullable=False),  # 'gmail', 'outlook', etc.
    Column("email", String, nullable=False),  # User's email address
    Column("access_token", String, nullable=False),  # OAuth access token
    Column("refresh_token", String, nullable=True),  # OAuth refresh token
    Column("token_type", String, nullable=True),  # Usually 'Bearer'
    Column("expires_at", TIMESTAMP, nullable=True),  # Token expiration timestamp
    Column("scope", String, nullable=True),  # OAuth scopes granted
    Column("created_at", TIMESTAMP, server_default=func.now(), nullable=False),
    Column("updated_at", TIMESTAMP, server_default=func.now(), onupdate=func.now(), nullable=False),
)

# Indices for oauth_tokens
Index("idx_oauth_tokens_provider", oauth_tokens.c.provider)
Index("idx_oauth_tokens_email", oauth_tokens.c.email)

species_info_cache = Table(
    "species_info_cache",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("species_name", String, nullable=False, unique=True),
    Column("title", String),
    Column("taxa_id", Integer),
    Column("source", String),
    Column("source_url", String),
    Column("description", String),
    Column("extract", String),
    Column("thumbnail_url", String),
    Column("wikipedia_url", String),
    Column("scientific_name", String),
    Column("conservation_status", String),
    Column("cached_at", TIMESTAMP, server_default=func.now()),
)

Index("idx_species_info_name", species_info_cache.c.species_name)
Index("idx_species_info_taxa_id", species_info_cache.c.taxa_id)
