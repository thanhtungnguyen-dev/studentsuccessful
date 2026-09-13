"""Conservative structured location resolution; raw values remain on JobLocation."""

import hashlib
import re

from sqlalchemy import func, select, text

from backend.app.models.taxonomy import Location

PROVINCES = {
    "ab": "Alberta",
    "alberta": "Alberta",
    "on": "Ontario",
    "ontario": "Ontario",
    "bc": "British Columbia",
    "british columbia": "British Columbia",
    "qc": "Quebec",
    "quebec": "Quebec",
}


def structured_location(raw):
    value = re.sub(r"^remote\s*[-\u2013]\s*", "", raw, flags=re.I).strip()
    if value.casefold() in {"canada", "ca"}:
        return None  # Country-only remote scope must not fabricate a city.
    parts = [part.strip() for part in value.split(",")]
    if len(parts) in {2, 3} and parts[1].casefold() in PROVINCES:
        if len(parts) == 3 and parts[2].casefold() not in {"canada", "ca"}:
            return None
        if not re.fullmatch(r"[\w .'-]{1,100}", parts[0]):
            return None
        return "CA", PROVINCES[parts[1].casefold()], parts[0]
    return None


def resolve_location(session, raw):
    parts = structured_location(raw)
    if not parts:
        return None
    country, region, city = parts
    key = int.from_bytes(
        hashlib.sha256(repr(parts).casefold().encode()).digest()[:8], "big", signed=True
    )
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    matches = session.scalars(
        select(Location)
        .where(
            Location.country_code == country,
            func.lower(Location.state_province) == region.casefold(),
            func.lower(Location.city) == city.casefold(),
        )
        .limit(2)
    ).all()
    if len(matches) > 1:
        return None
    if matches:
        return matches[0].id
    location = Location(country_code=country, state_province=region, city=city)
    session.add(location)
    session.flush()
    return location.id


def title_facts(title):
    """Only explicit title labels; ambiguous titles keep unspecified dimensions."""
    normalized = " ".join(title.casefold().split())
    employment = "UNSPECIFIED"
    level = "UNSPECIFIED"
    if re.search(r"\bco[ -]?op\b", normalized):
        employment, level = "CO_OP", "STUDENT"
    elif re.search(r"\bintern(?:ship)?\b", normalized) and not re.search(
        r"\b(manager|director|recruiter)\b", normalized
    ):
        employment, level = "INTERNSHIP", "STUDENT"
    elif re.search(r"\bnew[ -]grad(?:uate)?\b", normalized):
        employment, level = "NEW_GRAD", "ENTRY"
    role = None
    if re.search(
        r"\b(swe|software (engineer(?:ing)?|developer)|backend (software )?engineer)\b", normalized
    ):
        role = "Software Engineer"
    return role, employment, level
