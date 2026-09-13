"""Small persistence support for configured public live-job sources."""

from __future__ import annotations

import hashlib

from sqlalchemy import func, select

from backend.app.models.taxonomy import Company, Role


class LiveJobIngestionRepository:
    """Ensures only operator-configured shared catalog labels exist.

    Provider payloads never create taxonomy rows.  The company and role values
    here come from a locally configured source, so a new board can be enabled
    without a code change or a hidden manual database prerequisite.
    """

    def __init__(self, session):
        self.session = session

    def _unambiguous(self, statement):
        rows = self.session.scalars(statement.limit(2)).all()
        if len(rows) > 1:
            raise ValueError("configured catalog name is ambiguous")
        return rows[0] if rows else None

    def ensure_configured_catalog(self, company_name: str, role_name: str) -> None:
        company = self._unambiguous(
            select(Company).where(func.lower(Company.name) == company_name.casefold())
        )
        if company is None:
            self.session.add(Company(name=company_name, is_verified=False))

        role = self._unambiguous(
            select(Role).where(
                func.lower(Role.name) == role_name.casefold(), Role.is_active.is_(True)
            )
        )
        if role is None:
            slug = "live-" + hashlib.sha256(role_name.casefold().encode("utf-8")).hexdigest()[:24]
            slug_owner = self.session.scalar(select(Role).where(Role.slug == slug))
            if slug_owner is not None and slug_owner.name.casefold() != role_name.casefold():
                raise ValueError("configured role slug collides with an existing role")
            if slug_owner is None:
                self.session.add(Role(name=role_name, slug=slug, is_active=True))
        self.session.flush()


__all__ = ["LiveJobIngestionRepository"]
