"""Canonical source identity and bounded discovery detection (no network)."""

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from backend.app.ingestion.live import LiveJobSourceConfig
from backend.app.ingestion.public_http import public_url


def source_identity(config: LiveJobSourceConfig) -> str:
    value = {
        "greenhouse": config.board_token,
        "lever": config.site,
        "ashby": config.job_board,
        "smartrecruiters": config.company_identifier,
        "rss": config.feed_url,
        "recruitee": config.public_board_url,
        "personio": config.public_board_url,
        "jsonld": config.public_board_url,
        "workable": config.public_board_url,
        "teamtailor": config.public_board_url,
    }[config.family]
    if config.family == "workable":
        return urlsplit(value).path.strip("/").lower()
    if config.family in {"recruitee", "personio", "teamtailor"}:
        return urlsplit(value).hostname.lower()
    if config.family in {"rss", "jsonld"}:
        p = urlsplit(value)
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/", p.query, ""))
    return (config.region + ":" if config.family == "lever" else "") + value.lower()


def detect_source(url: str, company: str) -> LiveJobSourceConfig | None:
    public_url(url)
    p = urlsplit(url)
    host = p.hostname.lower()
    parts = [x for x in p.path.split("/") if x]
    family = field = value = None
    region = "global"
    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"} and parts:
        family, field, value = "greenhouse", "board_token", parts[0]
    elif host == "boards-api.greenhouse.io" and len(parts) >= 3 and parts[:2] == ["v1", "boards"]:
        family, field, value = "greenhouse", "board_token", parts[2]
    elif host in {"jobs.lever.co", "jobs.eu.lever.co"} and parts:
        family, field, value = "lever", "site", parts[0]
        region = "eu" if host == "jobs.eu.lever.co" else "global"
    elif (
        host in {"api.lever.co", "api.eu.lever.co"}
        and len(parts) >= 3
        and parts[:2] == ["v0", "postings"]
    ):
        family, field, value = "lever", "site", parts[2]
        region = "eu" if host == "api.eu.lever.co" else "global"
    elif (
        host == "api.ashbyhq.com" and len(parts) >= 3 and parts[:2] == ["posting-api", "job-board"]
    ):
        family, field, value = "ashby", "job_board", parts[2]
    elif host == "api.smartrecruiters.com" and len(parts) >= 3 and parts[:2] == ["v1", "companies"]:
        family, field, value = "smartrecruiters", "company_identifier", parts[2]
    elif host == "api.smartrecruiters.com" and len(parts) >= 2 and parts[0] == "companies":
        family, field, value = "smartrecruiters", "company_identifier", parts[1]
    elif host == "jobs.ashbyhq.com" and parts:
        family, field, value = "ashby", "job_board", parts[0]
    elif host == "jobs.smartrecruiters.com" and parts:
        family, field, value = "smartrecruiters", "company_identifier", parts[0]
    elif re.fullmatch(r"[a-z0-9-]+\.recruitee\.com", host):
        family, field, value = "recruitee", "public_board_url", f"https://{host}"
    elif re.fullmatch(r"[a-z0-9-]+\.jobs\.personio\.(de|com)", host):
        family, field, value = "personio", "public_board_url", f"https://{host}"
    elif (
        host == "apply.workable.com"
        and len(parts) == 5
        and parts[:4] == ["api", "v1", "widget", "accounts"]
    ):
        family, field, value = (
            "workable",
            "public_board_url",
            f"https://apply.workable.com/{parts[4]}",
        )
    elif host == "apply.workable.com" and parts and parts[0] not in {"j", "api"}:
        family, field, value = (
            "workable",
            "public_board_url",
            f"https://apply.workable.com/{parts[0]}",
        )
    elif host == "www.workable.com" and len(parts) == 3 and parts[:2] == ["api", "accounts"]:
        family, field, value = (
            "workable",
            "public_board_url",
            f"https://apply.workable.com/{parts[2]}",
        )
    elif re.fullmatch(r"[a-z0-9-]+\.workable\.com", host) and host.split(".")[0] not in {
        "www",
        "apply",
        "help",
    }:
        family, field, value = (
            "workable",
            "public_board_url",
            f"https://apply.workable.com/{host.split('.')[0]}",
        )
    elif re.fullmatch(r"[a-z0-9-]+\.teamtailor\.com", host) and host.split(".")[0] not in {
        "app",
        "support",
        "api",
        "www",
    }:
        family, field, value = "teamtailor", "public_board_url", f"https://{host}"
    if not family:
        return None
    config = LiveJobSourceConfig(
        key="candidate",
        family=family,
        company=company,
        region=region,
        max_postings=50,
        **{field: value},
    )
    key = (
        "discovered-"
        + hashlib.sha256((family + ":" + source_identity(config)).encode()).hexdigest()[:32]
    )
    return config.model_copy(update={"key": key})


def detect_content(url: str, company: str, content: str):
    """Recognize structured evidence, never guess a provider from arbitrary page text."""
    import xml.etree.ElementTree as ET

    from backend.app.ingestion.structured import jsonld_jobs

    config = detect_source(url, company)
    if config:
        return config
    family = None
    if jsonld_jobs(content):
        family = "jsonld"
    elif "<!DOCTYPE" not in content.upper() and "<!ENTITY" not in content.upper():
        try:
            root = ET.fromstring(content)
            if root.tag in {"rss", "{http://www.w3.org/2005/Atom}feed"}:
                family = "rss"
                if any(
                    node.tag.startswith("{https://teamtailor.com/locations}")
                    for node in root.iter()
                ):
                    family = "teamtailor"
        except (ET.ParseError, ValueError):
            pass
    if not family:
        return None
    p = urlsplit(url)
    value = f"https://{p.netloc}" if family == "teamtailor" else url
    config = LiveJobSourceConfig(
        key="candidate",
        family=family,
        company=company,
        max_postings=50,
        **{"feed_url" if family == "rss" else "public_board_url": value},
    )
    key = (
        "discovered-"
        + hashlib.sha256((family + ":" + source_identity(config)).encode()).hexdigest()[:32]
    )
    return config.model_copy(update={"key": key})
