"""Real public structures, safe read-only calibration and conservative normalization."""

import json
import threading
import time

import httpx
import pytest
from sqlalchemy import func, select

from backend.app.core.unit_of_work import UnitOfWork
from backend.app.ingestion.adapters import SourceAdapterRegistry
from backend.app.ingestion.live import (
    _employment_type,
    _work_mode,
    create_live_adapter,
)
from backend.app.ingestion.normalization import (
    _CANADIAN_REGIONS,
    remote_scope,
    structured_location,
    title_facts,
)
from backend.app.ingestion.source_detection import detect_content, detect_source, source_identity
from backend.app.models.job import JobLocation, NormalizedJob
from backend.app.services.canonical_jobs import canonical_url_fingerprint
from backend.app.services.coverage_calibration import (
    DEFAULT_FIXTURE,
    _percentile,
    calibrate,
    error_category,
)
from backend.app.services.live_job_ingestion import LiveJobIngestionService
from backend.app.services.source_quality import quality_report
from backend.tests.test_canonical_jobs import ingest, record, seed_catalog


@pytest.mark.parametrize(
    "url,provider,identity",
    [
        (
            "https://apply.workable.com/huggingface/j/ABC/apply?utm_source=test",
            "workable",
            "huggingface",
        ),
        ("https://huggingface.workable.com/jobs/123/candidates/new", "workable", "huggingface"),
        (
            "https://www.workable.com/api/accounts/huggingface?details=true",
            "workable",
            "huggingface",
        ),
        (
            "https://apply.workable.com/api/v1/widget/accounts/huggingface",
            "workable",
            "huggingface",
        ),
        ("https://career.teamtailor.com/jobs/123-title/", "teamtailor", "career.teamtailor.com"),
        (
            "https://career.teamtailor.com/jobs/456-title?utm_source=a",
            "teamtailor",
            "career.teamtailor.com",
        ),
        (
            "https://api.smartrecruiters.com/v1/companies/Visa/postings/123",
            "smartrecruiters",
            "visa",
        ),
    ],
)
def test_provider_source_identity(url, provider, identity):
    config = detect_source(url, "Example")
    assert config.family == provider and source_identity(config) == identity


@pytest.mark.parametrize(
    "url",
    [
        "https://apply.workable.com/j/ABC",
        "https://jobs.workable.com.evil.example/acme",
        "https://app.teamtailor.com",
        "https://nvidia.wd5.myworkdayjobs.com/site",
    ],
)
def test_unsupported_or_accountless_is_not_guessed(url):
    assert detect_source(url, "Example") is None


def fixture_adapter(key, company, provider):
    page = json.loads((DEFAULT_FIXTURE.parent / "fixtures" / f"{key}.json").read_text())[
        "responses"
    ][0]
    config = detect_content(page["url"], company, page["content"])
    assert config.family == provider
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(page["status"], text=page["content"])
        )
    )
    return create_live_adapter(config, client=client), client


@pytest.mark.parametrize(
    "key,company,provider",
    [
        ("huggingface", "Hugging Face", "workable"),
        ("blueground", "Blueground", "workable"),
        ("teamtailor", "Teamtailor", "teamtailor"),
        ("bunq", "bunq", "recruitee"),
    ],
)
def test_actual_public_structural_fixtures(key, company, provider):
    adapter, client = fixture_adapter(key, company, provider)
    with client:
        result = adapter.fetch_with_metadata()
    assert len(result.records) == 2 and result.skipped_records == 0
    assert all(
        row.application_url.startswith("https://") and row.external_id and row.locations
        for row in result.records
    )
    if key == "huggingface":
        assert result.records[0].work_mode == "REMOTE"
        assert result.records[0].posted_at is None  # public source only supplies a date
    if key == "bunq":
        assert result.records[0].posted_at.tzinfo is not None
        assert result.records[0].employment_type == "INTERNSHIP"


@pytest.mark.parametrize(
    "family,body", [("workable", '{"jobs":[]}'), ("teamtailor", "<rss><channel/></rss>")]
)
def test_valid_empty(family, body):
    config = detect_source(
        "https://apply.workable.com/example"
        if family == "workable"
        else "https://career.teamtailor.com",
        "Example",
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    ) as client:
        result = create_live_adapter(config, client=client).fetch_with_metadata()
    assert result.complete_listing and not result.records and not result.skipped_records


@pytest.mark.parametrize("family", ["workable", "teamtailor"])
@pytest.mark.parametrize(
    "status,expected", [(403, "HTTP_403"), (404, "HTTP_404"), (429, "HTTP_429"), (503, "HTTP_5XX")]
)
def test_provider_errors(family, status, expected):
    config = detect_source(
        "https://apply.workable.com/example"
        if family == "workable"
        else "https://career.teamtailor.com",
        "Example",
    )
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status))) as client:
        with pytest.raises(Exception) as error:
            create_live_adapter(config, client=client).fetch()
    assert error_category(error.value) == expected


def test_teamtailor_pagination_and_repeated_page_guard():
    # Exercise paging independently of the smaller normal per-cycle collection cap.
    config = detect_source("https://career.teamtailor.com", "Teamtailor").model_copy(
        update={"max_postings": 201}
    )
    calls = []

    def response(request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            text="<rss><channel>"
            + "".join(f"<item><guid>{i}</guid></item>" for i in range(100))
            + "</channel></rss>",
        )

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(Exception, match="Repeated Teamtailor page"):
            create_live_adapter(config, client=client).fetch()
    assert len(calls) == 2 and "offset=100" in calls[1]


@pytest.mark.parametrize("code,name", list(_CANADIAN_REGIONS.items()))
def test_all_canadian_regions(code, name):
    assert structured_location(f"Test City, {code}") == ("CA", name, "Test City")
    assert structured_location(f"Test City, {name}, Canada") == ("CA", name, "Test City")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Seattle, WA", ("US", "Washington", "Seattle")),
        ("Austin, Texas, USA", ("US", "Texas", "Austin")),
        ("Los Angeles, CA", ("US", "California", "Los Angeles")),
        ("Calgary, AB, US", None),
        ("Remote, CA", None),
        ("Remote Canada", None),
        ("Paris, ON, France", None),
    ],
)
def test_us_and_ambiguous_locations(raw, expected):
    assert structured_location(raw) == expected


@pytest.mark.parametrize(
    "title,role",
    [
        ("Frontend Engineer", "Frontend Engineer"),
        ("Full-stack Developer", "Full Stack Engineer"),
        ("Android Engineer", "Mobile Engineer"),
        ("Cloud Engineer", "Infrastructure Engineer"),
        ("SRE", "Site Reliability Engineer"),
        ("DevOps Engineer", "DevOps Engineer"),
        ("Firmware Engineer", "Embedded Software Engineer"),
        ("Security Engineer", "Security Engineer"),
        ("Data Engineer", "Data Engineer"),
        ("Machine Learning Engineer", "Machine Learning Engineer"),
        ("AI Engineer", "AI Engineer"),
        ("Research Engineer", "Research Engineer"),
        ("Robotics Software Engineer", "Robotics Engineer"),
        ("Computer Vision Engineer", "Computer Vision Engineer"),
        ("Compiler Engineer", "Systems Engineer"),
        ("Database Engineer", "Systems Engineer"),
        ("Backend Engineer", "Software Engineer"),
        ("Account Executive", None),
    ],
)
def test_cs_roles(title, role):
    assert title_facts(title)[0] == role


@pytest.mark.parametrize(
    "title,employment,level",
    [
        ("Summer Intern", "INTERNSHIP", "STUDENT"),
        ("Cooperative Education", "CO_OP", "STUDENT"),
        ("University Graduate", "NEW_GRAD", "ENTRY"),
        ("Graduate Program", "NEW_GRAD", "ENTRY"),
        ("Early Career Engineer", "UNSPECIFIED", "ENTRY"),
        ("Entry-Level Engineer", "UNSPECIFIED", "ENTRY"),
        ("Junior Engineer", "UNSPECIFIED", "ENTRY"),
        ("Senior Engineer", "UNSPECIFIED", "SENIOR"),
        ("Staff Engineer", "UNSPECIFIED", "STAFF"),
        ("Principal Engineer", "UNSPECIFIED", "PRINCIPAL"),
        ("Lead Engineer", "UNSPECIFIED", "LEAD"),
        ("Mid-level Engineer", "UNSPECIFIED", "MID"),
        ("Associate Engineer", "UNSPECIFIED", "ASSOCIATE"),
        ("Intern Program Manager", "UNSPECIFIED", "UNSPECIFIED"),
        ("Engineer", "UNSPECIFIED", "UNSPECIFIED"),
    ],
)
def test_employment_and_seniority(title, employment, level):
    assert title_facts(title)[1:] == (employment, level)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Student Intern", "INTERNSHIP"),
        ("Coop", "CO_OP"),
        ("Cooperative Education", "CO_OP"),
        ("Full Time", "FULL_TIME"),
        ("Part Time", "PART_TIME"),
        ("Temporary", "TEMPORARY"),
        ("Permanent", "UNSPECIFIED"),
        ("Early Career", "UNSPECIFIED"),
    ],
)
def test_explicit_type_values(value, expected):
    assert _employment_type(value) == expected


def test_work_mode_and_scope_do_not_imply_eligibility():
    assert _work_mode("on_site") == "ON_SITE"
    assert _work_mode("hybrid") == "HYBRID"
    assert _work_mode("sometimes remote") == "UNSPECIFIED"
    assert remote_scope("Remote Canada") == "CA"
    assert remote_scope("Remote") is None


def test_offline_command_never_fetches_or_opens_uow(monkeypatch, capsys):
    from backend.app.commands import job_intelligence

    monkeypatch.setattr(
        job_intelligence, "UnitOfWork", lambda: pytest.fail("No database access allowed")
    )
    monkeypatch.setattr(
        "sys.argv", ["job_intelligence", "coverage-calibrate", "--limit", "5", "--json"]
    )
    job_intelligence.main()
    output = json.loads(capsys.readouterr().out)
    assert output["database_writes"] == 0 and output["jobs_observed"] == 6
    assert (
        output["sources_fetch_success"] == 3
        and output["sources_fetch_failure"] == 1
        and output["sources_unknown"] == 1
    )


@pytest.mark.parametrize("kwargs", [{"limit": 41}, {"concurrency": 5}, {"timeout": 31}])
def test_calibration_bounds(kwargs):
    with pytest.raises(ValueError):
        calibrate(**kwargs)


def test_metrics_do_not_fabricate_unavailable_values():
    report = calibrate(limit=5, fetch=lambda *a, **kw: pytest.fail("Offline means no network"))
    assert report["unique_canonical_jobs"] is None
    assert report["ingestion_lag"] is None
    assert report["verified_official_apply_rate"] is None
    assert report["unknown_providers"][0]["probable_family"] == "workday"
    assert _percentile([1, 2, 3], 0.95) is None
    assert _percentile(list(range(20)), 0.5) == 9.5


def test_calibration_live_readonly_and_concurrency(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "company": f"Example{i}",
                        "url": f"https://apply.workable.com/example{i}",
                        "provider": "workable",
                    }
                    for i in range(8)
                ]
            }
        )
    )
    lock = threading.Lock()
    active = peak = 0

    def fetch(url, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.01)
        with lock:
            active -= 1
        return httpx.Response(200, json={"jobs": []}, request=httpx.Request("GET", url))

    result = calibrate(path, live=True, concurrency=4, fetch=fetch)
    assert peak <= 4 and result["sources_valid_empty"] == 8 and result["database_writes"] == 0


def test_unsafe_candidate_is_rejected_before_network(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps({"sources": [{"company": "Unsafe", "url": "http://169.254.169.254/latest"}]})
    )
    result = calibrate(
        path, live=True, fetch=lambda *a, **kw: pytest.fail("Must not fetch private host")
    )
    assert result["error_categories"] == {"NETWORK_SAFETY_REJECTION": 1}


@pytest.mark.parametrize("second_locations", [("Toronto, Canada",), ("Calgary, AB",)])
def test_workable_distinct_requisitions_shared_source_page_and_tracking(isolated_database, second_locations):
    seed_catalog(isolated_database)
    one = ingest(
        record(
            external_id="one",
            source_url="https://example.com/jobs",
            application_url="https://apply.workable.com/j/ONE",
        )
    )
    two = ingest(
        record(
            external_id="two",
            source_url="https://example.com/jobs",
            application_url="https://apply.workable.com/j/TWO",
            locations=second_locations,
        )
    )
    assert one != two
    duplicate = ingest(
        record(
            adapter_key="fixture.direct",
            external_id="official-one",
            application_url="https://apply.workable.com/j/ONE/apply?utm_source=board",
        ),
        "OFFICIAL_ATS",
    )
    assert duplicate == one
    assert canonical_url_fingerprint(
        "https://apply.workable.com/j/ONE/apply"
    ) == canonical_url_fingerprint("https://apply.workable.com/j/ONE")


def test_new_provider_ingestion_multi_location_and_inventory(isolated_database):
    seed_catalog(isolated_database)
    adapter, client = fixture_adapter("huggingface", "Hugging Face", "workable")
    with client:
        result = LiveJobIngestionService.ingest_adapter(adapter, SourceAdapterRegistry([adapter]))
    assert result.ingested == 2
    with UnitOfWork() as uow:
        report = quality_report(uow.session)
        assert report["inventory"]["canonical_jobs"] == 2
        assert report["inventory"]["official_canonical_preference"] == 2
        assert report["inventory"]["independently_verified_apply_rate"] is None
    job = ingest(record(external_id="multi", locations=("Calgary, AB", "Austin, TX")))
    assert (
        isolated_database.scalar(
            select(func.count())
            .select_from(JobLocation)
            .where(JobLocation.job_id == job, JobLocation.location_id.is_not(None))
        )
        == 2
    )


def test_duplicate_input_sources_are_not_probed_twice(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {"company": "Example", "url": url}
                    for url in [
                        "https://apply.workable.com/example",
                        "https://apply.workable.com/example/j/ABC?utm_source=x",
                    ]
                ]
            }
        )
    )
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"jobs": []}, request=httpx.Request("GET", url))

    report = calibrate(path, live=True, fetch=fetch)
    assert (
        len(calls) == 1 and report["sources_probed"] == 1 and report["duplicate_input_sources"] == 1
    )
    assert report["sources_fetch_failure"] == 0


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ReadTimeout("timeout"), "TIMEOUT"),
        (httpx.ConnectError("Public DNS resolution failed"), "DNS_ERROR"),
        (ValueError("Redirect limit"), "REDIRECT_FAILURE"),
        (ValueError("Private address"), "NETWORK_SAFETY_REJECTION"),
        (ValueError("Response too large"), "INVALID_RESPONSE"),
    ],
)
def test_error_taxonomy(error, expected):
    assert error_category(error) == expected


def test_new_provider_replay_is_offline_and_side_effect_free(isolated_database):
    from backend.app.services.source_intelligence import preserve_fetch, replay_fetch

    adapter, client = fixture_adapter("teamtailor", "Teamtailor", "teamtailor")
    with client:
        expected = adapter.fetch_with_metadata()
        digest = preserve_fetch(adapter)
    replay = replay_fetch(adapter.key, digest)
    assert replay.records == expected.records
    assert isolated_database.scalar(select(func.count()).select_from(NormalizedJob)) == 0


@pytest.mark.parametrize("family", ["workable", "teamtailor"])
def test_malformed_public_response_is_not_empty(family):
    config = detect_source(
        "https://apply.workable.com/example"
        if family == "workable"
        else "https://career.teamtailor.com",
        "Example",
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not a provider document"))
    ) as client:
        with pytest.raises(Exception) as error:
            create_live_adapter(config, client=client).fetch()
    assert error_category(error.value) == "INVALID_RESPONSE"


def test_workable_employer_mismatch_is_not_registered_as_verified():
    config = detect_source("https://apply.workable.com/example", "Unrelated Employer")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"name": "Actual Employer", "jobs": []})
        )
    ) as client:
        with pytest.raises(Exception, match="employer differs"):
            create_live_adapter(config, client=client).fetch()
