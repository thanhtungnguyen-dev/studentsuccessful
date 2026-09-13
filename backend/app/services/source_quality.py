"""Versioned, transparent source quality and success scheduling signals."""

from sqlalchemy import func, select

from backend.app.models.base import utc_now
from backend.app.models.job import JobSourceObservation, JobSourceRecord, LiveSourceState


def adaptive_interval(
    baseline: int,
    *,
    changed: bool,
    new_jobs: int,
    unchanged: int,
    recovering: bool = False,
    demand: float = 0,
) -> int:
    if recovering:
        return min(86400, max(300, baseline))
    if changed or new_jobs:
        interval = baseline // 2
    else:
        interval = baseline * min(8, 2 ** min(3, unchanged // 4))
    # Extension point only: aggregate demand is not collected per user.
    interval = int(interval * (1 - min(0.1, max(0, demand))))
    return min(86400, max(300, interval))


def quality_report(session):
    reports = []
    for state in session.scalars(select(LiveSourceState).order_by(LiveSourceState.source_key)):

        def ratio(n, d):
            return round(n / d, 4) if d else None

        reports.append(
            {
                "version": "source-quality-v2",
                "source": state.source_key,
                "health": state.health,
                "reliability": ratio(
                    state.total_collection_attempts - state.total_collection_failures,
                    state.total_collection_attempts,
                ),
                "ingestion_success": ratio(state.total_jobs_ingested, state.total_jobs_observed),
                "new_vacancies": state.total_new_canonical_jobs,
                "duplicate_contributions": state.total_duplicate_contributions,
                "official_apply_contributions": state.total_official_apply_urls,
                "last_verified": state.last_success_at,
                "last_change": state.last_change_at,
                "unchanged_polls": state.unchanged_successes,
                "next_poll": state.next_poll_at,
            }
        )
    clock = utc_now()
    observations = session.execute(
        select(JobSourceRecord.source_adapter, JobSourceObservation).join(
            JobSourceObservation, JobSourceObservation.job_source_record_id == JobSourceRecord.id
        )
    ).all()
    by_source = {}
    for source, observation in observations:
        by_source.setdefault(source, []).append(observation)
    for report in reports:
        rows = by_source.get(report["source"], [])
        report["completeness"] = (
            round(
                sum(
                    sum(
                        (
                            bool(obs.description),
                            obs.work_mode != "UNSPECIFIED",
                            obs.employment_type != "UNSPECIFIED",
                            obs.posted_at is not None,
                            bool((obs.fact_projection or {}).get("locations")),
                        )
                    )
                    / 5
                    for obs in rows
                )
                / len(rows),
                4,
            )
            if rows
            else None
        )
        report["stale_fraction"] = (
            round(
                sum(obs.explicitly_closed or obs.consecutive_absent_successes > 0 for obs in rows)
                / len(rows),
                4,
            )
            if rows
            else None
        )
        lags = [
            max(0, (obs.first_seen_at - obs.posted_at).total_seconds())
            for obs in rows
            if obs.posted_at
        ]
        report["mean_discovery_lag_seconds"] = round(sum(lags) / len(lags), 2) if lags else None
        report["verification_age_seconds"] = (
            max(0, (clock - report["last_verified"]).total_seconds())
            if report["last_verified"]
            else None
        )
    authority = dict(
        session.execute(
            select(JobSourceObservation.source_authority, func.count()).group_by(
                JobSourceObservation.source_authority
            )
        ).all()
    )
    return {"sources": reports, "observation_authority": authority}
