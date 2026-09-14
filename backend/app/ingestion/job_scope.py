"""Deterministic CA/US technical scope, before catalog or ingestion writes."""

import re
from dataclasses import dataclass

from backend.app.ingestion.normalization import (
    PROVINCES,
    ROLE_PATTERNS,
    STATES,
    structured_location,
    title_facts,
)

# Unambiguous major cities explicitly requested by product scope; never employer inference.
_CA_CITIES = {
    "toronto",
    "vancouver",
    "calgary",
    "waterloo",
    "ottawa",
    "montreal",
    "montréal",
    "edmonton",
}
_US_CITIES = {"seattle", "san francisco", "new york", "new york city", "austin", "boston"}
_OUTSIDE = {
    "london",
    "berlin",
    "singapore",
    "taipei",
    "taiwan",
    "germany",
    "united kingdom",
    "uk",
    "india",
    "china",
    "japan",
    "australia",
    "france",
}
_PROVINCE_NAMES = frozenset(v.casefold() for v in PROVINCES.values())
_STATE_NAMES = frozenset(v.casefold() for v in STATES.values())
_KNOWN_ROLES = frozenset(name.casefold() for _, name in ROLE_PATTERNS)
_NONTECH = re.compile(
    r"\b(?:marketing|recruit(?:er|ing|ment)|accounting|accountant|sales|retail|legal|nurs(?:e|ing)|human resources|hr|administrative|financial analyst|operations (?:intern|associate|coordinator)|office manager)\b",
    re.I,
)
_EXTRA_TECH = re.compile(
    r"\b(?:data scientist|analytics engineer|sdet|software test(?:ing)? engineer|qa automation(?: engineer)?|quant(?:itative)? (?:developer|research(?:er)?)|production engineer|applied scientist|security research(?:er)?|(?:application|infrastructure) security|software intern|developer co[ -]?op|performance engineer)\b",
    re.I,
)


@dataclass(frozen=True)
class ScopeDecision:
    accepted: bool
    geography: str
    technical: bool
    employment_type: str
    career_level: str
    priority: str
    reason: str


def geography(locations):
    found = set()
    for raw in locations:
        for value in re.split(r"[;|\n]", raw):
            value = value.strip()
            structured = structured_location(value)
            if structured:
                found.add(structured[0])
                continue
            normalized = re.sub(r"[._–-]+", " ", value.casefold())
            normalized = " ".join(normalized.split())
            # An explicit contradictory country must not be rescued by a city token.
            parts = [p.strip() for p in normalized.split(",")]
            if len(parts) > 1 and parts[-1] in _OUTSIDE:
                found.add("OUTSIDE")
                continue
            core = re.sub(r"\bremote\b", "", normalized).strip(" ,-")
            if core in {"canada", "ca"} or core in _CA_CITIES:
                found.add("CA")
            elif (
                core in {"us", "u s", "usa", "united states", "united states of america"}
                or core in _US_CITIES
            ):
                found.add("US")
            elif core == "north america" and "remote" in normalized:
                found.add("NORTH_AMERICA")
            elif core in _PROVINCE_NAMES:
                found.add("CA")
            elif core in _STATE_NAMES:
                found.add("US")
            elif len(parts) >= 2 and parts[-1] in {
                "canada",
                "us",
                "usa",
                "united states",
                "united states of america",
            }:
                found.add("CA" if parts[-1] == "canada" else "US")
            elif core in _OUTSIDE or core == "worldwide":
                found.add("OUTSIDE")
    if "NORTH_AMERICA" in found or {"CA", "US"} <= found:
        return "NORTH_AMERICA"
    return next((v for v in ("CA", "US", "OUTSIDE") if v in found), "UNKNOWN")


def classify_job(record):
    geo = geography(record.locations)
    role, employment, level = title_facts(
        re.sub(r"\bengineering\b", "engineer", record.title, flags=re.I)
    )
    normalized_role = record.role.casefold()
    technical = bool(role or normalized_role in _KNOWN_ROLES or _EXTRA_TECH.search(record.title))
    if _NONTECH.search(record.title):
        technical = False
    elif not technical and re.search(
        r"\b(?:data analyst|solutions engineer|ml intern|ai intern)\b", record.title, re.I
    ):
        technical = bool(
            re.search(
                r"\b(?:python|sql|pytorch|tensorflow|software development|data pipelines)\b",
                record.description or "",
                re.I,
            )
        ) or bool(re.search(r"\b(?:ml|ai) intern\b", record.title, re.I))
    if re.search(r"\bsolutions engineer\b", record.title, re.I) and re.search(
        r"\b(?:sales quota|sales targets|account executive|commission based)\b",
        record.description or "",
        re.I,
    ):
        technical = False
    if re.search(r"\bapplied scientist\b", record.title, re.I) and not role:
        technical = bool(
            re.search(
                r"\b(?:python|machine learning|computer vision|pytorch|tensorflow|software)\b",
                record.description or "",
                re.I,
            )
        )
    employment = record.employment_type if record.employment_type != "UNSPECIFIED" else employment
    level = record.career_level if record.career_level != "UNSPECIFIED" else level
    if level == "UNSPECIFIED" and re.search(r"\bstudent\b", record.title, re.I):
        level = "STUDENT"
    if employment in {"INTERNSHIP", "CO_OP"}:
        priority = "VERY_HIGH"
    elif employment == "NEW_GRAD" or level in {"ENTRY", "STUDENT"}:
        priority = "HIGH"
    elif level in {"SENIOR", "STAFF", "PRINCIPAL", "LEAD"} or employment in {
        "PART_TIME",
        "CONTRACT",
    }:
        priority = "LOWER"
    else:
        priority = "NORMAL"
    accepted = geo in {"CA", "US", "NORTH_AMERICA"} and technical
    return ScopeDecision(
        accepted,
        geo,
        technical,
        employment,
        level,
        priority,
        "accepted"
        if accepted
        else "geography"
        if geo in {"OUTSIDE", "UNKNOWN"}
        else "nontechnical",
    )


def scoped_records(records):
    accepted = []
    for record in records:
        decision = classify_job(record)
        if decision.accepted:
            accepted.append(
                record.model_copy(
                    update={
                        "employment_type": decision.employment_type,
                        "career_level": decision.career_level,
                    }
                )
            )
    return tuple(accepted)
