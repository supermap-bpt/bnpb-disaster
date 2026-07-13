import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base


class SavedSatellite(Base):
    __tablename__ = "saved_satellites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    satellite_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String, nullable=False)
    directory_path: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    product: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    instrument: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    platform: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    other: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    download_single_file: Mapped[str] = mapped_column(String, nullable=False)
    preview: Mapped[str | None] = mapped_column(String, nullable=True)
    footprint: Mapped[dict] = mapped_column(JSONB, nullable=False)
    mission: Mapped[str] = mapped_column(String, nullable=False)
    instrument_name: Mapped[str | None] = mapped_column(String, nullable=True)
    polarisation: Mapped[str] = mapped_column(String, nullable=False)
    sensing_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    size: Mapped[str] = mapped_column(String, nullable=False)
    product_file_status: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    product_file_path: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LandslideJob(Base):
    __tablename__ = "landslide_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Pre-event (earlier) and post-event (later) saved products paired for change detection.
    pre_satellite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    post_satellite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # pending | processing | completed | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    stage: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Keep in sync with app/services/landslide.py's TOTAL_STAGES.
    total_stages: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    threshold_db: Mapped[str] = mapped_column(String, nullable=False, default="-2.0")
    result_path: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FloodJob(Base):
    __tablename__ = "flood_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Single product - unlike LandslideJob's pre/post pair, Flood processes one scene.
    satellite_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # pending | processing | completed | failed
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    message: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    stage: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    stage_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Keep in sync with app/services/flood.py's TOTAL_STAGES.
    total_stages: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    threshold_sigma0: Mapped[str] = mapped_column(String, nullable=False, default="0.0137")
    result_path: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="in_progress")
    description: Mapped[str] = mapped_column(String, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
