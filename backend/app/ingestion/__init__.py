"""Internal job-source adapters and ingestion contracts.

This package intentionally has no HTTP router.  Jobs arrive through a trusted
adapter boundary and are written only by :mod:`backend.app.services.job_ingestion`.
"""

from backend.app.ingestion.adapters import SourceAdapter, SourceAdapterRegistry
from backend.app.ingestion.dto import (
    ExternalJobDTO,
    ExternalJobEducationRequirement,
    ExternalJobEligibilityRequirement,
    ExternalJobSkillRequirement,
)

__all__ = [
    "ExternalJobDTO",
    "ExternalJobEducationRequirement",
    "ExternalJobEligibilityRequirement",
    "ExternalJobSkillRequirement",
    "SourceAdapter",
    "SourceAdapterRegistry",
]
