import uuid

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SavedSatellite


class DuplicateSatelliteNameError(Exception):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f'A saved satellite named "{name}" already exists.')


class SatelliteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, **fields) -> SavedSatellite:
        record = SavedSatellite(**fields)
        self._session.add(record)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateSatelliteNameError(fields["satellite_name"]) from exc
        await self._session.refresh(record)
        return record

    async def list_filtered(
        self,
        *,
        name: str | None = None,
        date_from: date | None = None,
        date_until: date | None = None,
        offset: int = 0,
        limit: int = 10,
    ) -> tuple[list[SavedSatellite], int]:
        stmt = select(SavedSatellite)
        if name:
            stmt = stmt.where(SavedSatellite.satellite_name.ilike(f"%{name}%"))
        if date_from:
            # Compare against an explicit UTC-aware datetime rather than a bare `date`: binding a
            # plain `date` against a `timestamptz` column lets Postgres implicitly cast it using
            # the session's `TimeZone` GUC, which is not guaranteed to be UTC (and isn't on this
            # dev DB). sensing_time is always stored as UTC, so the boundary must be too.
            stmt = stmt.where(
                SavedSatellite.sensing_time
                >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            )
        if date_until:
            stmt = stmt.where(
                SavedSatellite.sensing_time
                < datetime.combine(date_until + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(SavedSatellite.saved_at.desc()).offset(offset).limit(limit)
        records = list((await self._session.execute(stmt)).scalars().all())
        return records, total

    async def get(self, satellite_id: uuid.UUID) -> SavedSatellite | None:
        return await self._session.get(SavedSatellite, satellite_id)

    async def delete(self, satellite_id: uuid.UUID) -> bool:
        record = await self.get(satellite_id)
        if record is None:
            return False
        await self._session.delete(record)
        await self._session.commit()
        return True

    async def update_file_status(
        self, satellite_id: uuid.UUID, *, status: str, file_path: str | None = None
    ) -> None:
        record = await self._session.get(SavedSatellite, satellite_id)
        if record is None:
            return
        record.product_file_status = status
        if file_path is not None:
            record.product_file_path = file_path
        await self._session.commit()
