"""Persistence primitives for independent live-source collection state."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import select, text

from backend.app.models.job import LiveSourceHealth, LiveSourceState

if TYPE_CHECKING:
    from backend.app.ingestion.live import LiveJobSourceConfig


@dataclass(frozen=True)
class LiveSourceClaim:
    """A short-lived, durable lease for one independently collected source."""

    config: LiveJobSourceConfig
    token: UUID
    etag: str | None
    last_modified: str | None
    normal_poll_interval_seconds: int
    retrieval_cursor: str | None = None


class LiveSourceStateRepository:
    """Locks source rows only where a collector needs a durable state transition."""

    def __init__(self, session):
        self.session = session

    def synchronize_configurations(
        self,
        configs: Iterable[LiveJobSourceConfig],
        intervals: Mapping[str, int],
        now: datetime,
    ) -> None:
        configs = tuple(configs)
        if not configs:
            return
        self.session.execute(text("SELECT pg_advisory_xact_lock(260004)"))
        states = {
            state.source_key: state
            for state in self.session.scalars(
                select(LiveSourceState)
                .where(LiveSourceState.source_key.in_([config.key for config in configs]))
                .with_for_update()
            )
        }
        for config in configs:
            state = states.get(config.key)
            if state is None:
                state = LiveSourceState(
                    source_key=config.key,
                    source_family=config.family,
                    enabled=config.enabled,
                    health=(
                        LiveSourceHealth.STALE if config.enabled else LiveSourceHealth.DISABLED
                    ),
                    normal_poll_interval_seconds=intervals[config.key],
                    next_poll_at=now if config.enabled else None,
                    updated_at=now,
                )
                self.session.add(state)
                continue

            was_disabled = not state.enabled
            state.source_family = config.family
            state.enabled = config.enabled
            state.normal_poll_interval_seconds = intervals[config.key]
            state.updated_at = now
            if not config.enabled:
                state.health = LiveSourceHealth.DISABLED
                state.next_poll_at = None
                state.lease_token = None
                state.lease_expires_at = None
            elif was_disabled:
                state.health = LiveSourceHealth.STALE
                state.next_poll_at = now

        self.session.flush()

    def mark_stale(self, source_keys: Iterable[str], now: datetime) -> None:
        keys = tuple(source_keys)
        if not keys:
            return
        states = self.session.scalars(
            select(LiveSourceState)
            .where(LiveSourceState.source_key.in_(keys))
            .with_for_update()
        ).all()
        for state in states:
            if (
                state.enabled
                and state.last_success_at is not None
                and state.health in {LiveSourceHealth.HEALTHY, LiveSourceHealth.DEGRADED}
                and now - state.last_success_at
                > timedelta(seconds=state.normal_poll_interval_seconds * 2)
            ):
                state.health = LiveSourceHealth.STALE
                state.updated_at = now
        self.session.flush()

    def claim_due(
        self,
        configs: Iterable[LiveJobSourceConfig],
        now: datetime,
        *,
        force: bool,
        lease_seconds: int,
        limit: int | None = None,
    ) -> tuple[LiveSourceClaim, ...]:
        configs = tuple(sorted(configs, key=lambda config: config.key))
        if not configs:
            return ()
        self.session.execute(text("SELECT pg_advisory_xact_lock(260004)"))
        states = {
            state.source_key: state
            for state in self.session.scalars(
                select(LiveSourceState)
                .where(LiveSourceState.source_key.in_([config.key for config in configs]))
                .with_for_update()
            )
        }
        claims: list[LiveSourceClaim] = []
        configs = sorted(configs, key=lambda config: (
            states[config.key].next_poll_at or now if config.key in states else now, config.key
        ))
        for config in configs:
            if limit is not None and len(claims) >= limit:
                break
            state = states.get(config.key)
            if state is None or not state.enabled:
                continue
            if state.lease_expires_at is not None and state.lease_expires_at > now:
                continue
            if not force and state.next_poll_at is not None and state.next_poll_at > now:
                continue
            token = uuid4()
            state.lease_token = token
            state.lease_expires_at = now + timedelta(seconds=lease_seconds)
            state.last_attempt_at = now
            state.updated_at = now
            claims.append(
                LiveSourceClaim(
                    config=config,
                    token=token,
                    etag=state.etag,
                    last_modified=state.last_modified,
                    normal_poll_interval_seconds=state.normal_poll_interval_seconds,
                    retrieval_cursor=state.retrieval_cursor,
                )
            )
        self.session.flush()
        return tuple(claims)

    def claimed_state(self, source_key: str, token: UUID) -> LiveSourceState | None:
        state = self.session.scalar(
            select(LiveSourceState)
            .where(LiveSourceState.source_key == source_key)
            .with_for_update()
        )
        if state is None or state.lease_token != token:
            return None
        return state

    def list_states(self) -> tuple[LiveSourceState, ...]:
        return tuple(
            self.session.scalars(
                select(LiveSourceState).order_by(LiveSourceState.source_key)
            ).all()
        )


__all__ = ["LiveSourceClaim", "LiveSourceStateRepository"]
