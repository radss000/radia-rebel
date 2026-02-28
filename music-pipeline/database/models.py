"""SQLAlchemy models for the REBEL music pipeline.

This module provides a typed ORM representation for the ``audio_assets`` table
so downstream tasks (feature extraction, provenance audits) can rely on a
shared schema definition. The core API still uses psycopg2 directly, so this
module is optional until the rest of the stack migrates to SQLAlchemy.
"""

from __future__ import annotations

from datetime import datetime
import enum
from uuid import uuid4

from sqlalchemy import Column, Enum, Index, Integer, LargeBinary, Numeric, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import declarative_base


Base = declarative_base()


class ProviderType(str, enum.Enum):
    bandcamp = "bandcamp"
    discogs = "discogs"
    youtube_music = "youtube_music"
    spotify = "spotify"
    other = "other"


class RightsScope(str, enum.Enum):
    restricted = "restricted"
    analysis_only = "analysis_only"
    public_preview = "public_preview"


class FetchStatus(str, enum.Enum):
    pending = "pending"
    fetched = "fetched"
    failed = "failed"
    purged = "purged"


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        Index(
            "idx_audio_assets_provider_track",
            "provider_type",
            "provider_track_id",
            unique=True,
        ),
        Index(
            "idx_audio_assets_storage_checksum",
            "storage_checksum",
            postgresql_where="storage_checksum IS NOT NULL",
        ),
        Index("idx_audio_assets_fetch_status", "fetch_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    track_id = Column(Integer, nullable=True, index=True)
    provider_type = Column(Enum(ProviderType, name="provider_type_enum"), nullable=False)
    provider_track_id = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    provider_preview_url = Column(Text)
    storage_path = Column(Text)
    storage_bucket_region = Column(Text)
    storage_checksum = Column(Text)
    audio_fingerprint = Column(LargeBinary)
    duration_seconds = Column(Numeric)
    bitrate_kbps = Column(Integer)
    rights_scope = Column(Enum(RightsScope, name="rights_scope_enum"), nullable=False, default=RightsScope.analysis_only)
    license_name = Column(Text)
    license_url = Column(Text)
    license_notes = Column(Text)
    fetched_at = Column(TIMESTAMP(timezone=True))
    expires_at = Column(TIMESTAMP(timezone=True))
    last_checked_at = Column(TIMESTAMP(timezone=True))
    fetch_status = Column(Enum(FetchStatus, name="fetch_status_enum"), nullable=False, default=FetchStatus.pending)
    fetch_attempts = Column(Integer, nullable=False, default=0)
    fetch_error = Column(Text)
    ingestion_job_id = Column(UUID(as_uuid=True))
    provenance_version = Column(Integer, nullable=False, default=1)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(TIMESTAMP(timezone=True))


__all__ = [
    "AudioAsset",
    "FetchStatus",
    "ProviderType",
    "RightsScope",
    "Base",
]
