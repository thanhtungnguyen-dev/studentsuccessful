"""Structured public sources; never CSS scraping or authenticated endpoints."""

import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

from backend.app.ingestion.live import (
    LiveSourceAdapter,
    LiveSourceFetchError,
    LiveSourceRecordError,
    _employment_type,
    _external_id,
    _feed_timestamp,
    _html_description,
    _html_to_text,
    _object,
    _public_https_url,
    _required_text,
    _work_mode,
)


def _record_url(value):
    try:
        return _public_https_url(value, "job URL")
    except (ValueError, TypeError) as exc:
        raise LiveSourceRecordError("Invalid job URL") from exc


class RecruiteeAdapter(LiveSourceAdapter):
    family = "recruitee"

    def _records(self):
        host = urlsplit(self.config.public_board_url).hostname
        data = _object(self._get_json(f"https://{host}/api/offers/"), "Recruitee response")
        if not isinstance(data.get("offers"), list):
            raise LiveSourceFetchError("Missing offers", category="MALFORMED_RESPONSE")
        return data["offers"]

    def _parse_record(self, raw):
        row = _object(raw, "offer")
        url = _required_text(row, "careers_url")
        apply = row.get("careers_apply_url") or url
        _record_url(url)
        _record_url(apply)
        locations = row.get("locations") or []
        if not isinstance(locations, list):
            raise LiveSourceRecordError("Invalid locations")
        values = []
        for location in locations:
            location = _object(location, "location")
            parts = [location.get(k) for k in ("city", "state", "country") if location.get(k)]
            if not all(isinstance(part, str) for part in parts):
                raise LiveSourceRecordError("Invalid location fields")
            if parts:
                values.append(", ".join(parts))
        return self._build_dto(
            external_id=_external_id(row, "id"),
            source_url=url,
            application_url=apply,
            title=_required_text(row, "title"),
            description=_html_description(row, "description"),
            locations=tuple(values),
            posted_at=_feed_timestamp(row.get("published_at"), "published_at"),
            employment_type=_employment_type(row.get("employment_type")),
            work_mode=_work_mode(row.get("workplace_type")),
        )


class PersonioAdapter(LiveSourceAdapter):
    family = "personio"

    def _records(self):
        host = urlsplit(self.config.public_board_url).hostname
        root = self._get_xml(f"https://{host}/xml?language=en")
        if root.tag != "workzag-jobs":
            raise LiveSourceFetchError("Invalid Personio XML", category="MALFORMED_RESPONSE")
        return list(root.findall("position"))

    def _parse_record(self, raw):
        def value(name):
            return raw.findtext(name)

        identity, title = value("id"), value("name")
        if not identity or not identity.isdecimal() or not title:
            raise LiveSourceRecordError("Missing Personio identity")
        host = urlsplit(self.config.public_board_url).hostname
        url = f"https://{host}/job/{identity}"
        locations = [value("office")] + [x.text for x in raw.findall("additionalOffices/office")]
        description = " ".join(
            _html_to_text(x.text or "") for x in raw.findall("jobDescriptions/jobDescription/value")
        )
        return self._build_dto(
            external_id=identity,
            source_url=url,
            application_url=url,
            title=title,
            description=description or None,
            locations=tuple(x for x in locations if x),
            employment_type=_employment_type(value("employmentType")),
        )


class _JsonScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.active = dict(attrs).get("type", "").lower() == "application/ld+json"
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.scripts.append("".join(self.parts))
            self.active = False


def jsonld_jobs(content: str) -> list[dict]:
    parser = _JsonScripts()
    parser.feed(content)
    jobs = []
    for script in parser.scripts[:100]:
        try:
            data = json.loads(script)
        except (ValueError, RecursionError):
            continue
        pending = [(data, 0)]
        visited = 0
        while pending and visited < 2000:
            node, depth = pending.pop()
            visited += 1
            if depth > 12:
                continue
            if isinstance(node, list):
                pending.extend((x, depth + 1) for x in node[:250])
            elif isinstance(node, dict):
                kind = node.get("@type")
                if kind == "JobPosting" or isinstance(kind, list) and "JobPosting" in kind:
                    jobs.append(node)
                if "@graph" in node:
                    pending.append((node["@graph"], depth + 1))
    return jobs


class JsonLdAdapter(LiveSourceAdapter):
    family = "jsonld"

    def _records(self):
        content = self._get_response_content(self.config.public_board_url, accept="text/html")
        jobs = jsonld_jobs(content.decode("utf-8", errors="replace"))
        if not jobs:
            raise LiveSourceFetchError("No JobPosting evidence", category="MALFORMED_RESPONSE")
        # A multi-job page must supply distinct vacancy URLs, never one shared identity.
        self._single_job_page = len(jobs) == 1
        urls = [row.get("url") for row in jobs if isinstance(row.get("url"), str)]
        self._ambiguous_urls = {url for url in urls if urls.count(url) > 1}
        return jobs

    def _parse_record(self, raw):
        row = _object(raw, "JobPosting")
        organization = _object(row.get("hiringOrganization"), "hiringOrganization")
        # A page cannot silently change a seed's employer identity.
        from backend.app.services.job_ingestion import normalize_company_identity

        if (
            normalize_company_identity(_required_text(organization, "name")).casefold()
            != self.config.company.casefold()
        ):
            raise LiveSourceRecordError("Employer does not match source")
        url = row.get("url")
        if not url:
            if not self._single_job_page:
                raise LiveSourceRecordError("Ambiguous JobPosting identity")
            url = self.config.public_board_url
        _record_url(url)
        if url in self._ambiguous_urls:
            raise LiveSourceRecordError("Shared JobPosting URL is not a vacancy identity")
        locations = row.get("jobLocation") or []
        if isinstance(locations, dict):
            locations = [locations]
        if not isinstance(locations, list):
            raise LiveSourceRecordError("Invalid locations")
        values = []
        for item in locations:
            address = _object(_object(item, "location").get("address"), "address")
            parts = [
                address.get(k)
                for k in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(k)
            ]
            if not all(isinstance(x, str) for x in parts):
                raise LiveSourceRecordError("Unsupported location")
            if parts:
                values.append(", ".join(parts))
        employment = row.get("employmentType")
        if not isinstance(employment, str):
            employment = None
        return self._build_dto(
            external_id=url,
            source_url=url,
            application_url=url,
            title=_required_text(row, "title"),
            description=_html_description(row, "description"),
            locations=tuple(values),
            posted_at=_feed_timestamp(row.get("datePosted"), "datePosted"),
            employment_type=_employment_type(employment),
            work_mode="REMOTE" if row.get("jobLocationType") == "TELECOMMUTE" else "UNSPECIFIED",
        )
