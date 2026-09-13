"""Canonical job-feed queries with one joined private user-state projection."""

from sqlalchemy import and_, exists, false, func, literal, or_, select
from sqlalchemy.orm import aliased

from backend.app.models.job import (
    JobEducationRequirement,
    JobEligibilityRequirement,
    JobLifecycle,
    JobLocation,
    JobSkillRequirement,
    JobSourceObservation,
    JobSourceRecord,
    NormalizedJob,
    UserJobState,
)
from backend.app.models.taxonomy import Company, Location, Role, Skill


class JobRepository:
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _listing_query(user_id=None):
        selected_observation = aliased(JobSourceObservation)
        selected_source = aliased(JobSourceRecord)
        anchor_source = aliased(JobSourceRecord)
        fields = [
            NormalizedJob.id,
            NormalizedJob.title,
            NormalizedJob.description,
            NormalizedJob.company_id,
            Company.name.label("company_name"),
            NormalizedJob.role_id,
            Role.name.label("role_name"),
            NormalizedJob.employment_type,
            NormalizedJob.career_level,
            NormalizedJob.work_mode,
            NormalizedJob.application_url,
            NormalizedJob.posted_at,
            NormalizedJob.discovered_at,
            NormalizedJob.first_seen_at,
            NormalizedJob.last_seen_at,
            NormalizedJob.last_verified_at,
            NormalizedJob.canonical_updated_at,
            NormalizedJob.lifecycle,
            func.coalesce(
                selected_source.source_adapter,
                anchor_source.source_adapter,
            ).label("source_adapter"),
        ]
        state = None
        if user_id is None:
            fields.extend(
                [
                    literal(False).label("saved"),
                    literal(False).label("hidden"),
                    literal(None).label("viewed_at"),
                ]
            )
        else:
            state = aliased(UserJobState)
            fields.extend(
                [
                    func.coalesce(state.saved, false()).label("saved"),
                    func.coalesce(state.hidden, false()).label("hidden"),
                    state.viewed_at,
                ]
            )
        query = (
            select(*fields)
            .join(Company, Company.id == NormalizedJob.company_id)
            .join(Role, Role.id == NormalizedJob.role_id)
            .join(anchor_source, anchor_source.id == NormalizedJob.job_source_record_id)
            .outerjoin(
                selected_observation,
                selected_observation.id == NormalizedJob.canonical_source_observation_id,
            )
            .outerjoin(
                selected_source,
                selected_source.id == selected_observation.job_source_record_id,
            )
            .where(
                NormalizedJob.is_active.is_(True),
                NormalizedJob.lifecycle != JobLifecycle.CLOSED,
            )
        )
        if state is not None:
            query = query.outerjoin(
                state,
                and_(
                    state.user_id == user_id,
                    state.canonical_job_id == NormalizedJob.id,
                ),
            )
        return query, state

    @staticmethod
    def _ordering(sort: str):
        """Only fixed SQLAlchemy ordering expressions may be selected."""

        orders = {
            "newest": (NormalizedJob.first_seen_at.desc(), NormalizedJob.id.desc()),
            "oldest": (NormalizedJob.first_seen_at.asc(), NormalizedJob.id.asc()),
            "title_asc": (func.lower(NormalizedJob.title).asc(), NormalizedJob.id.asc()),
            "title_desc": (func.lower(NormalizedJob.title).desc(), NormalizedJob.id.desc()),
        }
        return orders[sort]

    @staticmethod
    def _apply_search(query, criteria):
        """Add literal structured predicates without candidate-state joins."""

        if criteria.keyword:
            query = query.where(
                or_(
                    NormalizedJob.title.icontains(criteria.keyword, autoescape=True),
                    Company.name.icontains(criteria.keyword, autoescape=True),
                    NormalizedJob.description.icontains(criteria.keyword, autoescape=True),
                )
            )
        if criteria.company:
            query = query.where(Company.name.icontains(criteria.company, autoescape=True))
        if criteria.location:
            query = query.where(
                exists(
                    select(JobLocation.id).where(
                        JobLocation.job_id == NormalizedJob.id,
                        JobLocation.location_raw.icontains(
                            criteria.location, autoescape=True
                        ),
                    )
                )
            )
        if criteria.roles:
            query = query.where(Role.slug.in_(criteria.roles))
        location_predicates = [JobLocation.job_id == NormalizedJob.id]
        if criteria.countries:
            location_predicates.append(Location.country_code.in_(criteria.countries))
        if criteria.regions:
            location_predicates.append(
                func.lower(Location.state_province).in_(
                    [value.casefold() for value in criteria.regions]
                )
            )
        if criteria.cities:
            location_predicates.append(
                func.lower(Location.city).in_([value.casefold() for value in criteria.cities])
            )
        if len(location_predicates) > 1:
            query = query.where(
                exists(
                    select(JobLocation.id)
                    .join(Location, Location.id == JobLocation.location_id)
                    .where(*location_predicates)
                )
            )
        if criteria.requirement:
            query = query.where(
                exists(
                    select(JobSkillRequirement.id)
                    .join(Skill, Skill.id == JobSkillRequirement.skill_id)
                    .where(
                        JobSkillRequirement.job_id == NormalizedJob.id,
                        or_(
                            Skill.name.icontains(criteria.requirement, autoescape=True),
                            JobSkillRequirement.description.icontains(
                                criteria.requirement, autoescape=True
                            ),
                        ),
                    )
                )
            )
        if criteria.job_types:
            query = query.where(NormalizedJob.employment_type.in_(criteria.job_types))
        if criteria.work_modes:
            query = query.where(NormalizedJob.work_mode.in_(criteria.work_modes))
        if criteria.first_seen_after is not None:
            query = query.where(NormalizedJob.first_seen_at >= criteria.first_seen_after)
        return query

    @staticmethod
    def _apply_view(query, criteria, state):
        if criteria.view == "all":
            return query if state is None else query.where(
                or_(state.hidden.is_(None), state.hidden.is_(False))
            )
        if state is None:
            return query.where(false())
        if criteria.view == "saved":
            return query.where(
                state.saved.is_(True),
                or_(state.hidden.is_(None), state.hidden.is_(False)),
            )
        return query.where(state.hidden.is_(True))

    def search_active(self, criteria, user_id=None):
        """Return a count and a deterministic canonical page from one predicate."""

        query, state = self._listing_query(user_id)
        query = self._apply_view(self._apply_search(query, criteria), criteria, state)
        total = self.session.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        rows = list(
            self.session.execute(
                query.order_by(*self._ordering(criteria.sort))
                .offset((criteria.page - 1) * criteria.page_size)
                .limit(criteria.page_size)
            )
        )
        return int(total or 0), rows

    def matches_active_job(self, job_id, criteria) -> bool:
        """Test one canonical job with the exact Phase 22 listing predicate."""

        query, _ = self._listing_query()
        query = self._apply_search(query, criteria).where(NormalizedJob.id == job_id).limit(1)
        return self.session.scalar(query) is not None

    def active(self, job_id, user_id=None):
        query, _ = self._listing_query(user_id)
        return self.session.execute(query.where(NormalizedJob.id == job_id)).one_or_none()

    def locations_for_active(self, job_id):
        return list(
            self.session.scalars(
                select(JobLocation.location_raw)
                .join(NormalizedJob, NormalizedJob.id == JobLocation.job_id)
                .where(
                    JobLocation.job_id == job_id,
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                )
                .order_by(JobLocation.location_raw, JobLocation.id)
            )
        )

    def skill_requirements_for_active(self, job_id):
        return list(
            self.session.execute(
                select(
                    JobSkillRequirement.skill_id,
                    Skill.name.label("skill_name"),
                    Skill.category.label("skill_category"),
                    JobSkillRequirement.importance,
                    JobSkillRequirement.description,
                )
                .select_from(JobSkillRequirement)
                .join(NormalizedJob, NormalizedJob.id == JobSkillRequirement.job_id)
                .join(Skill, Skill.id == JobSkillRequirement.skill_id)
                .where(
                    JobSkillRequirement.job_id == job_id,
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                )
                .order_by(Skill.name, Skill.id)
            )
        )

    def education_requirements_for_active(self, job_id):
        return list(
            self.session.execute(
                select(
                    JobEducationRequirement.id,
                    JobEducationRequirement.degree_level,
                    JobEducationRequirement.target_grad_start,
                    JobEducationRequirement.target_grad_end,
                )
                .join(NormalizedJob, NormalizedJob.id == JobEducationRequirement.job_id)
                .where(
                    JobEducationRequirement.job_id == job_id,
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                )
                .order_by(
                    JobEducationRequirement.degree_level,
                    JobEducationRequirement.target_grad_start.nulls_last(),
                    JobEducationRequirement.target_grad_end.nulls_last(),
                    JobEducationRequirement.id,
                )
            )
        )

    def eligibility_requirements_for_active(self, job_id):
        return list(
            self.session.execute(
                select(
                    JobEligibilityRequirement.id,
                    JobEligibilityRequirement.requirement_type,
                    JobEligibilityRequirement.value,
                    JobEligibilityRequirement.description,
                )
                .join(NormalizedJob, NormalizedJob.id == JobEligibilityRequirement.job_id)
                .where(
                    JobEligibilityRequirement.job_id == job_id,
                    NormalizedJob.is_active.is_(True),
                    NormalizedJob.lifecycle != JobLifecycle.CLOSED,
                )
                .order_by(
                    JobEligibilityRequirement.requirement_type,
                    JobEligibilityRequirement.value,
                    JobEligibilityRequirement.id,
                )
            )
        )
