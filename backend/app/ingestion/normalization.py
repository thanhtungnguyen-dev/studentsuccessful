"""Conservative structured location resolution; raw values remain on JobLocation."""

import hashlib
import re

from sqlalchemy import func, select, text

from backend.app.models.taxonomy import Location

_CANADIAN_REGIONS = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "ON": "Ontario",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "MB": "Manitoba",
    "NS": "Nova Scotia",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "PE": "Prince Edward Island",
    "YT": "Yukon",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
}
_US_REGIONS = dict(
    pair.split(":")
    for pair in (
        "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|DE:Delaware|"
        "FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|"
        "LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|MS:Mississippi|"
        "MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|NJ:New Jersey|NM:New Mexico|"
        "NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|"
        "RI:Rhode Island|SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|"
        "VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming|DC:District of Columbia"
    ).split("|")
)
PROVINCES = {
    key.casefold(): name for code, name in _CANADIAN_REGIONS.items() for key in (code, name)
}
PROVINCES["quebec"] = "Quebec"
PROVINCES["qu\u00e9bec"] = "Quebec"
STATES = {key.casefold(): name for code, name in _US_REGIONS.items() for key in (code, name)}


def structured_location(raw):
    value = re.sub(r"^remote\s*[-\u2013]\s*", "", raw, flags=re.I).strip()
    parts = [part.strip() for part in value.split(",")]
    if len(parts) not in {2, 3} or not re.fullmatch(r"[\w .'-]{1,100}", parts[0]):
        return None
    if parts[0].casefold() in {"remote", "multiple locations", "anywhere"}:
        return None
    region = parts[1].casefold()
    if region in PROVINCES:
        country, canonical = "CA", PROVINCES[region]
        aliases = {"ca", "canada"}
    elif region in STATES:
        country, canonical = "US", STATES[region]
        aliases = {"us", "usa", "united states", "united states of america"}
    else:
        return None
    if len(parts) == 3 and parts[2].casefold() not in aliases:
        return None
    return country, canonical, parts[0]


def remote_scope(raw):
    """Diagnostic evidence only: the Location model requires an actual city."""
    value = re.sub(r"[\s_-]+", " ", raw.casefold()).strip()
    return {
        "remote canada": "CA",
        "remote us": "US",
        "remote usa": "US",
        "remote north america": "NORTH_AMERICA",
        "remote worldwide": "WORLDWIDE",
    }.get(value)


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


ROLE_PATTERNS = (
    (r"\b(?:machine learning|ml) (?:engineer|scientist)\b", "Machine Learning Engineer"),
    (r"\b(?:artificial intelligence|ai) engineer\b", "AI Engineer"),
    (r"\bcomputer vision (?:engineer|scientist)\b", "Computer Vision Engineer"),
    (r"\brobotics? (?:software )?engineer\b", "Robotics Engineer"),
    (r"\bresearch engineer\b", "Research Engineer"),
    (r"\bdata engineer\b", "Data Engineer"),
    (r"\b(?:site reliability engineer|sre)\b", "Site Reliability Engineer"),
    (r"\bdevops(?: engineer)?\b", "DevOps Engineer"),
    (r"\b(?:security|cybersecurity) engineer\b", "Security Engineer"),
    (r"\b(?:embedded|firmware) (?:software )?engineer\b", "Embedded Software Engineer"),
    (r"\b(?:ios|android|mobile) (?:software )?(?:engineer|developer)\b", "Mobile Engineer"),
    (r"\bfront[ -]?end (?:software )?(?:engineer|developer)\b", "Frontend Engineer"),
    (r"\bfull[ -]?stack (?:software )?(?:engineer|developer)\b", "Full Stack Engineer"),
    (r"\b(?:platform|infrastructure|cloud) (?:software )?engineer\b", "Infrastructure Engineer"),
    (
        r"\b(?:systems|compiler|compilers|database|network|networking|graphics|hpc) (?:software )?engineer\b",
        "Systems Engineer",
    ),
    (
        r"\b(?:swe|software engineer(?:ing)?|software developer|backend (?:software )?engineer)\b",
        "Software Engineer",
    ),
)


def title_facts(title):
    normalized = " ".join(title.casefold().split())
    employment = level = "UNSPECIFIED"
    supervisor = bool(re.search(r"\b(manager|director|recruiter|head)\b", normalized))
    if not supervisor:
        if re.search(r"\b(?:co[ -]?op|cooperative education)\b", normalized):
            employment, level = "CO_OP", "STUDENT"
        elif re.search(r"\bintern(?:ship)?\b", normalized):
            employment, level = "INTERNSHIP", "STUDENT"
        elif re.search(
            r"\b(?:new[ -]grad(?:uate)?|university graduate|graduate program)\b", normalized
        ):
            employment, level = "NEW_GRAD", "ENTRY"
        elif re.search(r"\b(?:early career|entry[ -]level|junior|jr\.?)\b", normalized):
            level = "ENTRY"
        else:
            for pattern, value in (
                (r"\bprincipal\b", "PRINCIPAL"),
                (r"\bstaff\b", "STAFF"),
                (r"\bsenior\b|\bsr\.", "SENIOR"),
                (r"\blead\b", "LEAD"),
                (r"\bmid[ -]level\b", "MID"),
                (r"\bassociate\b", "ASSOCIATE"),
            ):
                if re.search(pattern, normalized):
                    level = value
                    break
    role = next((role for pattern, role in ROLE_PATTERNS if re.search(pattern, normalized)), None)
    return role, employment, level
