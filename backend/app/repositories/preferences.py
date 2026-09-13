"""Existing preference aggregate and read-only catalogs; no commits."""
from sqlalchemy import delete, func, or_, select

from backend.app.models.preference import (
    CareerPreference,
    CareerPreferenceCustomValue,
    UserPreferredCompany,
    UserPreferredIndustry,
    UserPreferredLocation,
    UserPreferredRole,
    UserPreferredSkill,
)
from backend.app.models.taxonomy import Company, Industry, Location, Role, Skill
from backend.app.models.user import User
from backend.app.schemas.preferences import Preferences, normalized_custom

SELECTIONS = {
    "role_ids": (Role, UserPreferredRole, "role_id"),
    "industry_ids": (Industry, UserPreferredIndustry, "industry_id"),
    "location_ids": (Location, UserPreferredLocation, "location_id"),
    "company_ids": (Company, UserPreferredCompany, "company_id"),
    "skill_ids": (Skill, UserPreferredSkill, "skill_id"),
}


class PreferencesRepository:
    def __init__(self, session):
        self.session = session

    def lock_owner(self, user_id, read=False):
        self.session.execute(select(User.id).where(User.id == user_id).with_for_update(read=read)).scalar_one()

    def read(self, user_id):
        record = self.session.scalar(select(CareerPreference).where(CareerPreference.user_id == user_id).execution_options(populate_existing=True))
        values = {field: list(self.session.scalars(select(getattr(join, column)).where(join.user_id == user_id))) for field, (_, join, column) in SELECTIONS.items()}
        if record is not None:
            values.update(work_modes=record.work_modes, employment_types=record.employment_types,
                          custom_values=[{"preference_type": row.preference_type, "value": row.value} for row in self.session.scalars(select(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == record.id))])
        return Preferences(**values)

    def exists(self, user_id):
        return self.session.scalar(select(CareerPreference.id).where(CareerPreference.user_id == user_id)) is not None

    def valid_ids(self, field, ids):
        model = SELECTIONS[field][0]
        # Prevent a concurrent taxonomy deletion between validation and insertion.
        return set(self.session.scalars(select(model.id).where(model.id.in_(ids)).order_by(model.id).with_for_update(read=True, key_share=True))) == set(ids)

    def replace(self, user_id, values):
        record = self.session.scalar(select(CareerPreference).where(CareerPreference.user_id == user_id).execution_options(populate_existing=True))
        if record is None:
            record = CareerPreference(user_id=user_id)
            self.session.add(record)
        record.work_modes = values.work_modes
        record.employment_types = values.employment_types
        self.session.flush()
        for field, (_, join, column) in SELECTIONS.items():
            self.session.execute(delete(join).where(join.user_id == user_id))
            self.session.add_all([join(user_id=user_id, **{column: id}) for id in getattr(values, field)])
        self.session.execute(delete(CareerPreferenceCustomValue).where(CareerPreferenceCustomValue.career_preference_id == record.id))
        self.session.add_all([CareerPreferenceCustomValue(career_preference_id=record.id, preference_type=x.preference_type, value=x.value, normalized_value=normalized_custom(x.value)) for x in values.custom_values])


class CatalogRepository:
    def __init__(self, session):
        self.session = session

    def list(self, model, q=None, active=None, category=None, country_code=None):
        query = select(model)
        if active is not None:
            query = query.where(model.is_active == active)
        if category is not None:
            query = query.where(model.category == category)
        if country_code is not None:
            query = query.where(model.country_code == country_code.upper())
        if q:
            columns = [model.city, model.state_province] if model is Location else [model.name]
            query = query.where(or_(*(column.icontains(q.strip(), autoescape=True) for column in columns)))
        ordering = [model.country_code, func.lower(model.city), model.state_province, model.id] if model is Location else [func.lower(model.name), model.id]
        return list(self.session.scalars(query.order_by(*ordering)))
