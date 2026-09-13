# Job Intelligence V2 operations

This extends the existing collector, ingestion service, canonical jobs, lifecycle,
server-side filters and alerts. It does not add another scheduler or change the
public API. Apply migration `c26d7e9f102a` before starting updated workers.
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
New families use the same DTO, ingestion, observations and canonicalization:

| family | configuration field | extraction |
| --- | --- | --- |
| recruitee | public_board_url | tenant `/api/offers/` public offers |
| personio | public_board_url | tenant `/xml?language=en` positions |
| jsonld | public_board_url | bounded `application/ld+json` JobPosting nodes |

Use only a public HTTPS URL and the actual employer in the source configuration.
Generic JobPosting organization must match that employer after company identity
normalization. Multi-job pages must provide unique vacancy URLs; shared/missing
identities are rejected. Generic pages have weaker authority than direct ATS.
Missing structured jobs on a generic page are a failed fetch, never closure
proof. Malformed rows cannot trigger absence reconciliation. No arbitrary HTML
crawler, Workday tenant protocol, Workable or Teamtailor authentication was added.

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

Explicit title labels supply internship/co-op/new-grad level and known software
role family when configuration leaves role unspecified. Explicit provider fields
win. Corporate suffix punctuation is normalized without conflating regional
entities. Unambiguous Canadian province/city strings resolve to shared Location
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
