"""Deterministic canonical job-feed queries with no recommendation ranking."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.app.core.config import settings
from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.job import JobLifecycle
from backend.app.repositories.job import JobRepository
from backend.app.schemas.job import (
    PublicJobDetailRead,
    PublicJobEducationRequirementRead,
    PublicJobEligibilityRequirementRead,
    PublicJobRead,
    PublicJobSearchRead,
    PublicJobSkillRequirementRead,
    SavedSearchCriteria,
)

_EMPLOYMENT_TYPES = frozenset(
    {"INTERNSHIP", "CO_OP", "FULL_TIME", "PART_TIME", "CONTRACT", "NEW_GRAD"}
)
_WORK_MODES = frozenset({"ON_SITE", "HYBRID", "REMOTE"})
_RECENCY_WINDOWS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "3d": timedelta(days=3),
    "7d": timedelta(days=7),
    "all": None,
}
_VIEWS = frozenset({"all", "saved", "hidden"})
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ROLE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_SOURCE_NAMES = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "smartrecruiters": "SmartRecruiters",
    "rss": "Public careers feed",
}


class JobSearchValidationError(ValueError):
    """A filter is malformed before it reaches PostgreSQL."""


def _text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    if _CONTROL.search(value):
        raise JobSearchValidationError(f"{field} must not contain control characters")
    normalized = " ".join(value.split())
    return normalized or None


def _values(values: Iterable[str] | str | None, field: str) -> tuple[str, ...]:
    if values is None:
        return ()
    raw_values = [values] if isinstance(values, str) else values
    normalized: list[str] = []
    for raw in raw_values:
        if not isinstance(raw, str):
            raise JobSearchValidationError(f"{field} must contain strings")
        for part in raw.split(","):
            value = _text(part, field)
            if value is not None:
                normalized.append(value)
    if len(normalized) > 20:
        raise JobSearchValidationError(f"Too many {field} selections")
    return tuple(dict.fromkeys(normalized))


def _choice_values(
    values: Iterable[str] | str | None,
    field: str,
    allowed: frozenset[str],
) -> tuple[str, ...]:
    canonical: list[str] = []
    for value in _values(values, field):
        choice = re.sub(r"[\s-]+", "_", value).upper()
        if choice not in allowed:
            raise JobSearchValidationError(f"Unsupported {field}")
        canonical.append(choice)
    return tuple(dict.fromkeys(canonical))


def _role_values(values: Iterable[str] | str | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in _values(values, "role"):
        slug = re.sub(r"[\s_]+", "-", value).casefold()
        if not _ROLE_SLUG.fullmatch(slug):
            raise JobSearchValidationError("Unsupported role")
        normalized.append(slug)
    return tuple(dict.fromkeys(normalized))


def _country_values(values: Iterable[str] | str | None) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in _values(values, "country"):
        code = value.upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise JobSearchValidationError("country must be a two-letter code")
        normalized.append(code)
    return tuple(dict.fromkeys(normalized))


def _location_values(
    values: Iterable[str] | str | None,
    field: str,
) -> tuple[str, ...]:
    return _values(values, field)


@dataclass(frozen=True)
class JobSearch:
    """Validated catalog criteria. OR applies inside each tuple; fields combine with AND."""

    keyword: str | None = None
    location: str | None = None
    company: str | None = None
    requirement: str | None = None
    roles: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    job_types: tuple[str, ...] = ()
    work_modes: tuple[str, ...] = ()
    recency: str = "all"
    view: str = "all"
    page: int = 1
    page_size: int = 10
    sort: str = "newest"

    @classmethod
    def from_request(
        cls,
        *,
        keyword: str | None = None,
        query: str | None = None,
        location: str | None = None,
        company: str | None = None,
        requirement: str | None = None,
        role: Iterable[str] | str | None = None,
        country: Iterable[str] | str | None = None,
        region: Iterable[str] | str | None = None,
        city: Iterable[str] | str | None = None,
        employment_type: Iterable[str] | str | None = None,
        job_type: Iterable[str] | str | None = None,
        type: Iterable[str] | str | None = None,
        work_mode: Iterable[str] | str | None = None,
        recency: str | None = None,
        view: str | None = None,
        page: int = 1,
        page_size: int = 10,
        sort: str = "newest",
    ) -> JobSearch:
        keyword_value = _text(keyword, "keyword")
        query_value = _text(query, "query")
        if keyword_value is not None and query_value is not None:
            raise JobSearchValidationError("Use either keyword or query, not both")
        job_type_groups = [
            values
            for values in (employment_type, job_type, type)
            if _values(values, "job_type")
        ]
        if len(job_type_groups) > 1:
            raise JobSearchValidationError(
                "Use one of employment_type, job_type, or type"
            )
        normalized_recency = (_text(recency, "recency") or "all").casefold()
        if normalized_recency not in _RECENCY_WINDOWS:
            raise JobSearchValidationError("Unsupported recency")
        normalized_view = (_text(view, "view") or "all").casefold()
        if normalized_view not in _VIEWS:
            raise JobSearchValidationError("Unsupported view")
        if sort not in {"newest", "oldest", "title_asc", "title_desc"}:
            raise JobSearchValidationError("Unsupported sort")
        return cls(
            keyword=keyword_value or query_value,
            location=_text(location, "location"),
            company=_text(company, "company"),
            requirement=_text(requirement, "requirement"),
            roles=_role_values(role),
            countries=_country_values(country),
            regions=_location_values(region, "region"),
            cities=_location_values(city, "city"),
            job_types=_choice_values(
                job_type_groups[0] if job_type_groups else None,
                "job_type",
                _EMPLOYMENT_TYPES,
            ),
            work_modes=_choice_values(work_mode, "work_mode", _WORK_MODES),
            recency=normalized_recency,
            view=normalized_view,
            page=page,
            page_size=page_size,
            sort=sort,
        )

    @classmethod
    def from_saved_criteria(cls, criteria: SavedSearchCriteria) -> JobSearch:
        return cls.from_request(
            keyword=criteria.keyword,
            company=criteria.company,
            requirement=criteria.requirement,
            role=criteria.roles,
            country=criteria.countries,
            region=criteria.regions,
            city=criteria.cities,
            job_type=criteria.job_types,
            work_mode=criteria.work_modes,
            recency=criteria.recency,
        )

    def to_saved_criteria(self) -> SavedSearchCriteria:
        return SavedSearchCriteria(
            roles=list(self.roles),
            countries=list(self.countries),
            regions=list(self.regions),
            cities=list(self.cities),
            job_types=list(self.job_types),
            work_modes=list(self.work_modes),
            recency=self.recency,
            keyword=self.keyword,
            company=self.company,
            requirement=self.requirement,
        )

    @property
    def first_seen_after(self) -> datetime | None:
        window = _RECENCY_WINDOWS[self.recency]
        return datetime.now(timezone.utc) - window if window is not None else None

    def matched_filter_labels(self) -> list[str]:
        """Human-readable facts about this query, never a candidate-fit claim."""

        labels: list[str] = []
        if self.roles:
            labels.append("Role: " + ", ".join(value.replace("-", " ").title() for value in self.roles))
        if self.countries:
            labels.append("Country: " + ", ".join(self.countries))
        if self.regions:
            labels.append("Region: " + ", ".join(self.regions))
        if self.cities:
            labels.append("City: " + ", ".join(self.cities))
        if self.job_types:
            labels.append(
                "Job type: "
                + ", ".join(value.replace("_", " ").title() for value in self.job_types)
            )
        if self.work_modes:
            labels.append(
                "Work mode: "
                + ", ".join(value.replace("_", " ").title() for value in self.work_modes)
            )
        if self.recency != "all":
            labels.append(
                {
                    "1h": "First seen: Last hour",
                    "24h": "First seen: Last 24 hours",
                    "3d": "First seen: Last 3 days",
                    "7d": "First seen: Last 7 days",
                }[self.recency]
            )
        if self.keyword:
            labels.append(f"Keyword: {self.keyword}")
        if self.company:
            labels.append(f"Company: {self.company}")
        if self.requirement:
            labels.append(f"Skill: {self.requirement}")
        return labels


class JobService:
    @staticmethod
    def _public_job(row, criteria: JobSearch | None = None) -> dict:
        values = dict(row._mapping)
        adapter_key = values.pop("source_adapter")
        family = adapter_key.split(".", 1)[0].casefold()
        values["source_name"] = _SOURCE_NAMES.get(family, "Official careers site")
        if (
            values["lifecycle"] == JobLifecycle.ACTIVE
            and datetime.now(timezone.utc) - values["first_seen_at"]
            <= timedelta(hours=settings.JOB_NEW_WINDOW_HOURS)
        ):
            values["lifecycle"] = "NEW"
        values["unseen"] = values["viewed_at"] is None
        values["matched_filters"] = criteria.matched_filter_labels() if criteria else []
        return values

    @staticmethod
    def list_active(
        criteria: JobSearch,
        uow,
        user_id,
    ) -> PublicJobSearchRead:
        total, rows = JobRepository(uow.session).search_active(criteria, user_id)
        total_pages = (total + criteria.page_size - 1) // criteria.page_size
        return PublicJobSearchRead(
            items=[
                PublicJobRead(**JobService._public_job(row, criteria))
                for row in rows
            ],
            page=criteria.page,
            page_size=criteria.page_size,
            total=total,
            total_pages=total_pages,
        )

    @staticmethod
    def get_active(job_id, uow, user_id=None) -> PublicJobDetailRead:
        repository = JobRepository(uow.session)
        row = repository.active(job_id, user_id)
        if row is None:
            raise StudentSuccessfulException(404, "JOB_NOT_FOUND", "Job not found")
        return PublicJobDetailRead(
            **JobService._public_job(row),
            locations=repository.locations_for_active(job_id),
            skill_requirements=[
                PublicJobSkillRequirementRead(**requirement._mapping)
                for requirement in repository.skill_requirements_for_active(job_id)
            ],
            education_requirements=[
                PublicJobEducationRequirementRead(**requirement._mapping)
                for requirement in repository.education_requirements_for_active(job_id)
            ],
            eligibility_requirements=[
                PublicJobEligibilityRequirementRead(**requirement._mapping)
                for requirement in repository.eligibility_requirements_for_active(job_id)
            ],
        )
