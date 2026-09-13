"""Owner-locked factual aggregates; no commits and no preference writes."""

from sqlalchemy import delete, select

from backend.app.core.exceptions import StudentSuccessfulException
from backend.app.models.base import utc_now
from backend.app.models.portfolio import Project, ProjectCustomSkill, ProjectSkill, UserCustomSkill
from backend.app.models.resume import UserSkill
from backend.app.models.taxonomy import Skill, SkillAlias
from backend.app.models.user import User
from backend.app.schemas.portfolio import ProjectRead, SkillSelection
from backend.app.schemas.preferences import normalized_custom


class PortfolioRepository:
    def __init__(self, session):
        self.session = session

    def lock_owner(self, owner, read=False):
        self.session.execute(
            select(User.id).where(User.id == owner).with_for_update(read=read)
        ).scalar_one()

    def validate(self, values):
        found = set(
            self.session.scalars(
                select(Skill.id)
                .where(Skill.id.in_(values.skill_ids))
                .order_by(Skill.id)
                .with_for_update(read=True, key_share=True)
            )
        )
        if found != set(values.skill_ids):
            raise StudentSuccessfulException(422, "INVALID_SKILL", "Unknown catalog skill")
        if values.custom_values:
            names = {normalized_custom(value) for value in self.session.scalars(select(Skill.name))}
            names.update(
                normalized_custom(value) for value in self.session.scalars(select(SkillAlias.alias))
            )
            if any(normalized_custom(value) in names for value in values.custom_values):
                raise StudentSuccessfulException(
                    422,
                    "DUPLICATE_CATALOG_SKILL",
                    "Choose the existing catalog skill instead of a duplicate custom value",
                )

    def skills(self, owner):
        return SkillSelection(
            skill_ids=list(
                self.session.scalars(
                    select(UserSkill.skill_id).where(
                        UserSkill.user_id == owner, UserSkill.confirmed_by_user.is_(True)
                    )
                )
            ),
            custom_values=list(
                self.session.scalars(
                    select(UserCustomSkill.value).where(UserCustomSkill.user_id == owner)
                )
            ),
        )

    def replace_skills(self, owner, values):
        # Keep retained rows/notes/source/timestamps stable; a save explicitly confirms new claims.
        existing = {
            row.skill_id: row
            for row in self.session.scalars(
                select(UserSkill)
                .where(UserSkill.user_id == owner)
                .execution_options(populate_existing=True)
            )
        }
        for id, row in existing.items():
            if row.confirmed_by_user and id not in values.skill_ids:
                self.session.delete(row)
        for id in values.skill_ids:
            if id not in existing:
                self.session.add(
                    UserSkill(user_id=owner, skill_id=id, source="USER", confirmed_by_user=True)
                )
            elif not existing[id].confirmed_by_user:
                existing[id].confirmed_by_user = True
                existing[id].confirmed_at = utc_now()
                existing[id].source = "USER"
        self.replace_custom(UserCustomSkill, "user_id", owner, values.custom_values)

    def replace_custom(self, model, field, owner, values):
        existing = {
            row.normalized_value: row
            for row in self.session.scalars(select(model).where(getattr(model, field) == owner))
        }
        wanted = {normalized_custom(value): value for value in values}
        for key, row in existing.items():
            if key not in wanted:
                self.session.delete(row)
            elif row.value != wanted[key]:
                row.value = wanted[key]
        for key, value in wanted.items():
            if key not in existing:
                self.session.add(model(**{field: owner}, value=value, normalized_value=key))

    def project(self, owner, id):
        row = self.session.scalar(
            select(Project)
            .where(Project.user_id == owner, Project.id == id)
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise StudentSuccessfulException(404, "PROJECT_NOT_FOUND", "Project not found")
        return row

    def project_read(self, row):
        return ProjectRead(
            id=row.id,
            title=row.title,
            description=row.description,
            project_url=row.project_url,
            repository_url=row.repository_url,
            created_at=row.created_at,
            updated_at=row.updated_at,
            technologies=SkillSelection(
                skill_ids=list(
                    self.session.scalars(
                        select(ProjectSkill.skill_id).where(ProjectSkill.project_id == row.id)
                    )
                ),
                custom_values=list(
                    self.session.scalars(
                        select(ProjectCustomSkill.value).where(
                            ProjectCustomSkill.project_id == row.id
                        )
                    )
                ),
            ),
        )

    def projects(self, owner):
        return [
            self.project_read(row)
            for row in self.session.scalars(
                select(Project)
                .where(Project.user_id == owner)
                .order_by(Project.created_at, Project.id)
            )
        ]

    def replace_technologies(self, id, values):
        self.session.execute(
            delete(ProjectSkill).where(
                ProjectSkill.project_id == id, ProjectSkill.skill_id.not_in(values.skill_ids)
            )
        )
        existing = set(
            self.session.scalars(select(ProjectSkill.skill_id).where(ProjectSkill.project_id == id))
        )
        self.session.add_all(
            [
                ProjectSkill(project_id=id, skill_id=skill)
                for skill in values.skill_ids
                if skill not in existing
            ]
        )
        self.replace_custom(ProjectCustomSkill, "project_id", id, values.custom_values)
