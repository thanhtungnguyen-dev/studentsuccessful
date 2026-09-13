# Job Intelligence V2 operations

This extends the existing collector, ingestion service, canonical jobs, lifecycle,
server-side filters and alerts. It does not add another scheduler or change the
public API. Apply migrations through `d27e8f0a213b` before starting updated workers.
The migration is forward-only; use a verified backup for disaster recovery.

## Enable discovery

Keep configured `LIVE_JOB_SOURCES_JSON` seeds. Set the backend-only
`LIVE_SOURCE_DISCOVERY_ENABLED=true` to opt in to automatic expansion.
The default is false. Existing persisted discoveries remain eligible for
collection when expansion is disabled; disable their `source_registry.enabled`
flag to stop collection. Explicit `--source`/`--family` CLI selectors restrict
collection and do not run discovery. No public management endpoint was added.

The existing collector combines configured seeds and persisted discoveries by
(provider, canonical identity). Configured seeds win, including disabled seeds.
A source key cannot be reassigned to a different board. Registry uniqueness and
transaction advisory locks prevent duplicate registrations and concurrent state
creation. Removed configured seeds are not silently converted to discoveries.

After ingestion commits, safe job/apply URLs enter a durable queue. Each cycle
leases at most three URLs, verifies them outside database transactions, and then
registers supported sources. New sources become eligible on the next cycle.
Redirects can reveal direct ATS boards; structured RSS/Atom and JobPosting pages
can be discovered without CSS scraping. Unknown pages remain measurable UNKNOWN
outcomes. Verification checks up to two postings, then collection uses the stored
limit (50 for discoveries). It is structural verification, not a guarantee of
employer identity or future provider availability.

The queue is capped at 5,000 records and the registry at 1,000 entries for automatic
registration. Terminal queue records expire after 30 days. Leases last ten minutes;
three failed attempts terminate work, including an expired final lease after a
crash. Temporary failures retry with backoff. Capacity exhaustion does not roll
back already ingested jobs. Query-bearing candidate URLs are not queued because
they may carry credentials/tokens. The input job contract still retains its source
URL according to the existing contract.

## HTTP boundaries

Public HTTP(S) GET only, standard ports, no embedded credentials, cookies, proxy,
or authentication. All DNS answers must be public; the socket connects directly to
one validated address while preserving TLS hostname verification. DNS is bounded
by ten seconds and eight outstanding resolver threads, connection by ten seconds,
and response body by a thirty-second total read deadline (shorter configured
limits apply). Every redirect is revalidated; maximum three during discovery,
none during normal adapter fetches. HTTPS downgrades fail. Responses are capped at
5 MiB; compressed responses are rejected rather than decompressed without a cap.
401/403, CAPTCHA and anti-bot failures are not bypassed. Discovery verification
requests are bounded and run outside ingestion transactions.

## Structured coverage

Existing Greenhouse, Lever, Ashby, SmartRecruiters and RSS/Atom adapters remain.
Additional families use the same DTO, ingestion, observations and canonicalization:

| family | configuration field | extraction |
| --- | --- | --- |
| recruitee | public_board_url | tenant `/api/offers/` public offers |
| personio | public_board_url | tenant `/xml?language=en` positions |
| jsonld | public_board_url | bounded `application/ld+json` JobPosting nodes |
| workable | public_board_url | canonical `https://apply.workable.com/ACCOUNT` public jobs |
| teamtailor | public_board_url | career-site root; documented public `/jobs.rss` |

Use only a public HTTPS URL and the actual employer in the source configuration.
Generic JobPosting organization must match that employer after company identity
normalization. Multi-job pages must provide unique vacancy URLs; shared/missing
identities are rejected. Generic pages have weaker authority than direct ATS.
Missing structured jobs on a generic page are a failed fetch, never closure
proof. Malformed rows cannot trigger absence reconciliation. No arbitrary HTML
crawler, Workday tenant protocol, or authenticated ATS API was added.

Provider references: [Recruitee offers](https://docs.recruitee.com/reference/offers),
[Recruitee authentication](https://docs.recruitee.com/reference/authentication-1),
[Personio XML](https://developer.personio.de/docs/retrieving-open-job-positions).
Public endpoint availability is provider-controlled; no live coverage totals are
claimed from offline fixtures.

## Evidence, replay and provenance

Complete fetches within an 8 MiB capture / 10 MiB serialized budget retain raw
response content, URL, HTTP/content metadata, source configuration, parser version,
content hash and first/last fetch time. Ten distinct fetches per source are kept.
Over-budget or incomplete capture is not presented as replayable evidence; normal
validated record snapshots still persist. Captures are backend operational data,
not exposed by the API. Replay is read-only and makes no network requests:

```sh
python -m backend.app.commands.job_intelligence report
python -m backend.app.commands.job_intelligence replay --source SOURCE_KEY --hash HASH
```

The report lists up to 100 recent capture hashes. Replay runs the current parser
against captured responses and reports parsed/malformed counts. It does not apply
new facts, advance lifecycle, or emit alerts. Historical payloads beyond retention
require a future refetch. Canonical field provenance references the responsible
observation for title/company/role, description, enums, dates, Apply URL and the
selected requirements/location projection. Existing records populate provenance
when they are next resolved. Fact changes record changed fields and before/after
snapshot hashes; repeat identical observations do not create change events.

## Normalization and identity

Explicit title labels supply internship/co-op/new-grad and seniority levels and known CS
role families when configuration leaves role unspecified. Explicit provider fields
win. Corporate suffix punctuation is normalized without conflating regional
entities. Unambiguous Canadian province/city and US state/city strings resolve to shared Location
rows; raw descriptions and multiple locations remain on one vacancy. Ambiguous
remote geography is not converted into a fictional city. Existing skills,
salary and eligibility projection continue unchanged; unsupported JSON-LD salary,
validThrough and applicantLocationRequirements remain only in raw evidence.

Existing provider/external IDs, canonical URL hashes and exact company/title/
location evidence remain in use. Known Lever/Recruitee application suffixes and
tracking parameters normalize to the same vacancy. Distinct known ATS URLs cannot
merge based only on a generic title/location. This deliberately prefers a missed
merge to a false merge. Existing authority chooses canonical facts and official
Apply destinations. No fuzzy company merger or inferred candidate facts was added.

## Scheduling and quality

Semantic DTO hashes detect changes independently of vendor JSON formatting.
Changed/new-job sources poll at half baseline; every four unchanged successes
increase the interval, capped at 8x baseline. Recovery first returns to baseline.
Success scheduling including jitter stays within 300–86,400 seconds. Existing
429/5xx/Retry-After exponential backoff, leases and provider baselines remain.
A bounded aggregate-demand parameter is an extension point only; no per-user
polling or demand query is enabled.

The versioned quality report separates operational health from reliability,
ingestion success, new/duplicate/official-Apply contributions, completeness,
stale fraction, discovery lag, verification age, authority mix, last change,
unchanged polls and next poll. Queue states expose unknown/failed opportunities.
This is a read-only operator report, not an opaque Candidate Fit score. Its
observation aggregation is intended for operator use, not every feed request.

NEWEST ordering, hard filters, saved searches, owner-scoped state, canonical alert
deduplication and Candidate Fit remain the existing implementation. Recommended
feed ordering is not added: current Fit evaluates one candidate/job and is not a
batch feed-ranking primitive. No frontend, auth, resume or production configuration
changes are required by this upgrade.

## Coverage calibration

Workable and Teamtailor are supported provider families. Workable uses the public
account endpoint's observed redirect destination (`apply.workable.com/api/v1/widget/accounts/...`),
not its authenticated SPI API. Teamtailor reuses the existing RSS record parser
and handles its structured location namespace and offset pagination. The normal
50-posting collection cap remains; feeds containing more jobs are not complete
absence evidence. Apply migration `d27e8f0a213b` before using these families.

References: [Workable public jobs API](https://workable.readme.io/reference/jobs-1)
and [Teamtailor RSS](https://support.teamtailor.com/en/articles/11171756-rss-feed-how-to-guide).
Workable's accountless `/j/SHORTCODE` URLs identify jobs but do not establish the
account; discovery leaves the account unknown rather than guessing it.

Run the reproducible calibration command from the repository root:

```sh
python -m backend.app.commands.job_intelligence coverage-calibrate --json
python -m backend.app.commands.job_intelligence coverage-calibrate --fixture backend/calibration/sources.json --live --json --limit 33 --concurrency 4 --timeout 10
python -m backend.app.commands.job_intelligence coverage-calibrate --provider workable --live --json
```

Default mode is offline, using small public structural fixtures. Entries without
fixtures are NOT_PROBED, not failed or successful live sources. Live mode is
explicit, makes no database connection, and does not register sources or ingest
jobs. No `--apply` mode exists. The 33-source dataset is developer/operator data,
not production source configuration or business logic. It spans technology,
AI/ML, infrastructure, semiconductors, autonomy, fintech, Canadian companies,
startups and a community feed. Its expected-provider labels are selection hints;
actual detection and success are measured independently.

Limits: at most 40 source entries, four concurrent probes, six successful HTTP responses per
source (plus one rejected oversized Greenhouse request), five parsed jobs per source, and existing response/redirect safety caps.
Equivalent detected input identities are probed once. Default examples use the
entire current set. Results are bounded samples, not full employer vacancy totals
or a representative estimate of student opportunity share. Company completeness
for generic RSS is unknown because the publisher is not necessarily the employer.

The JSON report separates SUCCESS, VALID_EMPTY_SOURCE, unsupported providers,
malformed parsing, DNS/timeouts, HTTP status categories, unsafe network targets,
redirect failures and invalid/oversized responses. Provider distributions, field
completeness, explicit job type/level/role counts and location scopes are diagnostic.
Source identity matches count discovery candidates; successful discovery means an
identity also passed the current probe, not that it was registered. Direct-source
rate uses successful official source authority, not independent verification of
Apply ownership. URL identity counts are not canonical-job counts or an exact
duplicate-leakage estimate.

Workday remains unsupported: sampled career sites returned a JavaScript shell or
an HTTP failure; this pass did not establish a supported public list/detail
contract with generalized pagination. It does not use browser automation or
reverse-engineer employer-specific selectors. Oversized Ashby boards remain rejected; its documented public posting API
has no pagination or lightweight list/detail contract. The cap was not relaxed. Date-only publication values remain
raw evidence, without invented time zones. Explicit UTC timestamps from Recruitee
are accepted. Salary and expiry remain raw evidence because the current DTO lacks
those canonical fields. Permanent duration does not imply full-time hours.

Geographic normalization covers all Canadian provinces/territories and US
states/DC, preserving contradictory or country-only locations as raw/unknown.
Remote country/continent labels are diagnostic only: the existing Location model
requires a real city and does not encode work authorization. Role and seniority
rules use explicit title labels; missing experience never implies entry level.

The existing database `report` additionally exposes inventory employment/level/
role counts, source authority, official canonical/Apply source preference, and
publication-to-first-seen lag. p50/p95 require at least 20 valid nonnegative samples.
No claimed independently verified Apply percentage is produced. Existing
300–86,400-second polling bounds, failure backoff, ranking, filters and alerts
remain unchanged. This one-time cross-section cannot calibrate longitudinal
polling performance, so no interval change was justified.


## Bounded Greenhouse large boards

Normal boards retain the one-request `content=true` path. Only an oversized
response selects the [documented Greenhouse list/detail API](https://docs.greenhouse.io/job-board.html).
The fallback requests the lightweight `/jobs` list without descriptions, sorts
unique numeric posting IDs, and fetches `/jobs/{id}` individually. Every response
still uses the 5 MiB limit and the existing public-host/DNS/timeout protections.
An oversized lightweight list or individual detail fails safely; no HTML fallback.

Each detail is ingested through the existing service before the next request.
Each source cycle processes at most `min(max_postings, 50)` details, stopping
between details after a 60-second elapsed budget. One in-flight bounded request
may overrun that budget. The initial cycle has at most 52 requests (rejected full
response, lightweight list, 50 details); subsequent cycles have at most 51.
Short lease renewals occur between batches, outside HTTP transactions.

Migration `e28f9a1b324c` adds only a nullable `retrieval_cursor` to source state.
These boards need multiple cycles, so this cursor prevents restarting at the
first IDs on every poll or worker restart. It includes the board identity and
last visited ID; `0` means the next pass starts at the beginning while retaining
list/detail mode. Changed/deleted/reordered IDs do not invalidate the keyset.
New lower IDs are visited after wraparound. Progress commits after ingestion;
a crash in that gap safely repeats an idempotent posting. No snapshot generation
or accumulated list of seen IDs is stored.

Nonempty fallback traversals always set `complete_listing=false`, including the
last batch: a mutable listing across cycles is not a provider snapshot. Thus
unvisited or removed jobs receive no absence increments or closure. Only an
authoritative empty lightweight list can supply empty-board evidence. Existing
small-board reconciliation thresholds are unchanged. Positive observations and
reopening still use existing lifecycle rules. Timeout, oversized detail, 5xx and
429 stop traversal; committed observations/cursors survive and normal failure
backoff (including Retry-After) wins. Useful partial failures retain counters
and are degraded, or rate-limited for 429, rather than erasing successful work.

Raw evidence is retained one detail response per existing evidence entry, with
the existing ten-entry retention. `greenhouse-detail-v1` evidence replays that
single detail offline without fetching a list or invoking lifecycle writes.
Calibration reports retrieval strategy and continuation, retaining its five-job
sample budget. Run only selected source fixtures when investigating large boards;
a sampled partial result is never a valid-empty board or a complete inventory.
