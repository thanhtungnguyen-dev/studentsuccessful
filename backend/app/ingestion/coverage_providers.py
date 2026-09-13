"""Documented public Workable jobs and Teamtailor RSS, using the existing adapter contract."""

import re
from urllib.parse import urlsplit

from backend.app.ingestion.live import (
    LiveSourceAdapter,
    LiveSourceFetchError,
    LiveSourceRecordError,
    _employment_type,
    _external_id,
    _feed_record,
    _feed_timestamp,
    _html_description,
    _object,
    _required_text,
    _work_mode,
)
from backend.app.ingestion.structured import _record_url


def public_timestamp(value):
    # Date-only values have no trustworthy time/zone. Keep them in raw evidence.
    if value is None or isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    return _feed_timestamp(value, "public timestamp")


class WorkableAdapter(LiveSourceAdapter):
    family = "workable"

    def _records(self):
        account = urlsplit(self.config.public_board_url).path.strip("/")
        data = _object(
            self._get_json(
                f"https://apply.workable.com/api/v1/widget/accounts/{account}",
                params={"details": "true"},
            ),
            "Workable account",
        )
        if not isinstance(data.get("jobs"), list):
            raise LiveSourceFetchError("Missing public jobs", category="MALFORMED_RESPONSE")
        if data.get("name"):
            from backend.app.services.job_ingestion import normalize_company_identity

            if (
                normalize_company_identity(data["name"]).casefold()
                != self.config.company.casefold()
            ):
                raise LiveSourceFetchError(
                    "Workable account employer differs from configured source",
                    category="MALFORMED_RESPONSE",
                )
        # The documented public API returns the account's published collection, not SPI pagination.
        return data["jobs"]

    def _parse_record(self, raw):
        row = _object(raw, "Workable job")
        identity = _required_text(row, "shortcode")
        url = _required_text(row, "url")
        apply = row.get("application_url") or url
        for value in (url, apply):
            _record_url(value)
            host = urlsplit(value).hostname
            if not host or not (host == "apply.workable.com" or host.endswith(".workable.com")):
                raise LiveSourceRecordError("Workable job has an unexpected destination")
        locations = row.get("locations")
        if locations is None:
            locations = [row]
        if not isinstance(locations, list):
            raise LiveSourceRecordError("Invalid Workable locations")
        values = []
        for item in locations:
            item = _object(item, "location")
            parts = [item.get("city"), item.get("region") or item.get("state"), item.get("country")]
            if any(part is not None and not isinstance(part, str) for part in parts):
                raise LiveSourceRecordError("Invalid location fields")
            if any(parts):
                values.append(", ".join(part for part in parts if part))
        mode = _work_mode(row.get("workplace_type"))
        if mode == "UNSPECIFIED" and row.get("telecommuting") is True:
            mode = "REMOTE"
        return self._build_dto(
            external_id=identity,
            source_url=url,
            application_url=apply,
            title=_required_text(row, "title"),
            description=_html_description(row, "description"),
            locations=tuple(dict.fromkeys(values)),
            employment_type=_employment_type(row.get("employment_type")),
            work_mode=mode,
            posted_at=public_timestamp(row.get("published_on")),
            source_updated_at=public_timestamp(row.get("updated_at")),
        )


class TeamtailorAdapter(LiveSourceAdapter):
    family = "teamtailor"

    def _records(self):
        url = self.config.public_board_url.rstrip("/") + "/jobs.rss"
        records = []
        seen = set()
        for offset in range(0, self.config.max_postings, 100):
            root = self._get_xml(
                url,
                params={"offset": offset} if offset else None,
                track_response_metadata=offset == 0,
            )
            channel = root.find("channel")
            if root.tag != "rss" or channel is None:
                raise LiveSourceFetchError("Invalid Teamtailor RSS", category="MALFORMED_RESPONSE")
            items = channel.findall("item")
            signature = tuple(item.findtext("guid") for item in items)
            if items and signature in seen:
                raise LiveSourceFetchError(
                    "Repeated Teamtailor page", category="MALFORMED_RESPONSE"
                )
            seen.add(signature)
            records.extend(items)
            if len(items) < 100:
                break
        return records

    def _parse_record(self, raw):
        row = _feed_record(raw, atom=False)
        url = _required_text(row, "source_url")
        _record_url(url)
        if urlsplit(url).hostname != urlsplit(self.config.public_board_url).hostname:
            raise LiveSourceRecordError("Teamtailor job escaped its career site")
        values = []
        ns = "{https://teamtailor.com/locations}"
        for location in raw.findall(f"{ns}locations/{ns}location"):
            parts = [location.findtext(ns + key) for key in ("city", "region", "country")]
            if any(parts):
                values.append(", ".join(part for part in parts if part))
            elif location.findtext(ns + "name"):
                values.append(location.findtext(ns + "name"))
        return self._build_dto(
            external_id=_external_id(row, "external_id"),
            source_url=url,
            application_url=url,
            title=_required_text(row, "title"),
            description=_html_description(row, "description"),
            locations=tuple(dict.fromkeys(values)),
            posted_at=public_timestamp(row.get("posted_at")),
            employment_type=_employment_type(row.get("employment_type")),
            work_mode=_work_mode(raw.findtext("remoteStatus")),
        )
