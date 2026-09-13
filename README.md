# StudentSuccessful engineering foundation

Next.js 15 / React / TypeScript â†’ FastAPI / SQLAlchemy â†’ PostgreSQL 16.
R5 adds browser registration, login, session persistence, and CSRF-protected logout.
Phases 6B–8B add explicit profile facts, preferences, projects, resumé versioning, and deterministic local resume evidence.
Phase 8C adds the read-only Candidate Profile, which reconciles source citations without creating new candidate facts.
Phase 9 adds shared, authenticated, read-only Job browsing over normalized job records and explicit requirements.
Phase 10 adds an internal job-ingestion foundation that reuses persisted source records and snapshots to create or update those shared normalized records.
Phase 11 adds deterministic, paginated discovery over that shared catalog without candidate matching or recommendations.
Phase 12 adds a private, derived candidate fit view for a selected job, with distinct evidence sources and explicit unknowns. See [fit analysis rules](docs/fit-analysis.md).
Compose remains development infrastructure. Phase 25 adds a separate
[`docker-compose.production.yml`](docker-compose.production.yml) deployment
definition and [production operations guide](docs/production.md); a real
hosting account, managed PostgreSQL, private object storage, and HTTPS domain
are still required before a production release.

## Docker setup

Install Docker Engine/Desktop with the Compose v2 plugin. Run all commands from the repository root.
Copy `.env.example` to `.env` (`cp .env.example .env` on Unix; `Copy-Item .env.example .env` in PowerShell).
For the default stack, leave ports 5432, 8000 and 3000 free.

```sh
docker compose config --quiet
docker compose up --build
```

Or start in the background and wait for readiness:

```sh
docker compose up --build -d --wait --wait-timeout 180
python scripts/smoke_compose.py
docker compose ps -a
```

Open http://localhost:3000. Backend docs: http://localhost:8000/docs.
The smoke command needs Python 3.13 on the host and only uses its standard library.
It verifies the page, direct and proxied health/readiness, an allowed-Origin login returning 401
for a nonexistent account, and a foreign-Origin request returning 403. It creates no accounts.

Startup is explicit: PostgreSQL healthy â†’ one-shot `migrate` succeeds â†’ backend readiness succeeds
(database and local storage) â†’ frontend starts and serves its page. A migration failure blocks the backend.
Inspect it with `docker compose logs migrate`. Check the schema with:

```sh
docker compose run --rm migrate python -m alembic -c backend/alembic.ini current --check-heads
docker compose run --rm migrate python -m alembic -c backend/alembic.ini check
```

The backend image builds from the repository root, preserving `/app/backend` with `/app` as working
directory. Its entrypoint constructs the database URL from the same `POSTGRES_USER`, `POSTGRES_PASSWORD`,
and `POSTGRES_DB` that initialize PostgreSQL, then executes either Alembic or Uvicorn. Percent-encoded
credentials are supported. Compose ignores the native `DATABASE_URL`; it cannot silently override these
credentials. PostgreSQL initialization variables apply only when the data volume is empty.

The Node 22 image runs `npm ci`, `npm run build`, then `npm run start`. It keeps build dependencies
because Next reads the TypeScript configuration at startup. Docker ignores exclude env files and local
build/data artifacts. Source bind mounts do not cover the compiled image; rebuild after code changes.

The browser requests same-origin `/api/*` and `/health/*`. Next proxies them to `http://backend:8000`.
`next build` captures rewrites in `.next/routes-manifest.json`, so Compose supplies
`BACKEND_INTERNAL_URL` as a **build argument** as well as a runtime variable. Changing just the runtime
variable does not relocate the built rewrites: rebuild. No backend credentials are exposed as
`NEXT_PUBLIC_*` variables. The supported local browser origin is `http://localhost:3000`.

Stop while retaining data:

```sh
docker compose down
```

### Fresh disposable verification and old volumes

The pre-production baseline `aba441bbcc36` was corrected in R2/R3 without a revision change.
A pre-R3 database stamped with that revision will NOT be repaired by `alembic upgrade head`.
Recreate pre-R3 **disposable** development databases once. Preserve valuable data and plan its migration separately.
Do not delete unknown volumes. For verification choose a unique project name that has never been used,
with the normal stack stopped so the ports are available. For example, replace `ss-r4-check-unique` below:

```sh
docker compose -p ss-r4-check-unique config --quiet
docker compose -p ss-r4-check-unique build
docker compose -p ss-r4-check-unique up -d --wait --wait-timeout 180
python scripts/smoke_compose.py
docker compose -p ss-r4-check-unique ps -a
# ONLY this new disposable verification project; destroys its DB and resume volume:
docker compose -p ss-r4-check-unique down --volumes --remove-orphans
```

## Native development

Use Python 3.13, Node 22.13+ within major 22, and PostgreSQL 16. Install and activate a Python virtual
environment from the repository root:

```sh
python -m venv .venv
# Unix:
source .venv/bin/activate
# PowerShell alternative:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

Copy the environment file as above. Run an existing PostgreSQL 16 server and create the development
DB, or start only the Compose PostgreSQL service: `docker compose up -d --wait postgres`.
Set `.env` DATABASE_URL to that database (default local credentials match Compose defaults).
Alembic uses DATABASE_MIGRATION_URL when it is configured, otherwise it falls
back to DATABASE_URL; use the optional direct/admin URL only for managed PostgreSQL.
From the repository root:

```sh
python -m alembic -c backend/alembic.ini upgrade head
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd frontend
npm ci
npm run dev
```

Next defaults to the native backend at `http://127.0.0.1:8000`. If needed, export `BACKEND_INTERNAL_URL`
in that shell before dev/build (PowerShell: `$env:BACKEND_INTERNAL_URL='http://127.0.0.1:8000'`).
The root `.env` is read by the backend and Compose, not Next. For a native production frontend build,
run `npm run build` followed by `npm run start`. HTTP development uses the `ss_session` cookie;
production requires Secure cookies, `__Host-ss_session`, and an HTTPS frontend origin.

## Verification

Frontend (from `frontend/`):

```sh
npm ci
npm run lint
npm run type-check
npm run test
npm run build
npm audit
```

ESLint 10 runs directly with TypeScript recommended rules and the Next 15 recommended/Core Web Vitals
rules. Next 15's embedded older lint runner is disabled; CI explicitly runs the real lint command before build.
Next is pinned to 15.5.24, the patched 15.x release in the August 2026 advisory:
https://nextjs.org/blog/august-2026-security-release . A targeted Next-only PostCSS override uses 8.5.28
(the existing project's PostCSS version) to address the audit findings in Next's pinned 8.4.31.

Backend tests destroy/rebuild their target schema. Create a separate, disposable PostgreSQL database
whose name contains `test`, e.g. `createdb -h localhost -U postgres studentsuccessful_test_local`.
Export these settings in the test shell (use `$env:NAME='value'` in PowerShell):

```sh
export APP_ENV=test
export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/studentsuccessful_test_local
export DATABASE_MIGRATION_URL=$DATABASE_URL
export TEST_DATABASE_URL=$DATABASE_URL
export ALLOW_DISPOSABLE_TEST_DATABASE=1
ruff check backend
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current --check-heads
python -m alembic -c backend/alembic.ini check
python -m pytest backend/tests/test_migrations.py backend/tests/test_postgresql_schema.py
python -m pytest backend/tests
```

Never point TEST_DATABASE_URL at a valuable database. Close the test shell afterward to avoid using its
settings for normal development. Alembic >=1.17.1 is required for `current --check-heads`.

Offline contract generation from the root (Python dependencies and `frontend/npm ci` installed):

```sh
python scripts/generate_api_client.py
python scripts/generate_api_client.py --check
```

No running API, database, or remote schema is used. `--check` generates in a temporary directory and
fails if either checked-in contract is stale, without overwriting it. The Bash wrapper delegates to the
same script. Commit both generated files when intentionally changing the API.

CI runs contract checking, PostgreSQL 16 migrations/schema/full tests and Ruff, frontend lint/typecheck/
Vitest/build, plus a 25-minute Compose smoke and browser-auth job. Every smoke job uses a unique disposable project and
cleans up only that project's volumes. A workflow definition is not evidence that remote Actions ran.

## Scope still pending

Public discovery search, matching, candidate fit, resume evaluation or rewriting,
application tracking, recommendations, workers, request IDs/global Problem Details, and production deployment
design remain deferred.
The baseline database schema is pre-production. Do not infer production deployment readiness from Compose.


## Browser authentication (R5)

Start the stack using the Docker commands above, then open http://localhost:3000.
Choose Register, enter your email, a password of 8–128 characters, and matching confirmation.
Registration establishes a session, confirms it with `/api/v1/auth/me`, and returns home showing your email.
Reloading or opening another tab checks the same server session. Logout reads the current `ss_csrf`
cookie, submits the protected mutation, and checks `/me` again. Other tabs recheck on focus or refresh.
Login accepts your existing credentials; incorrect credentials show a generic error. Application identity/contact facts are available at `/profile`. The HttpOnly session cookie is managed by the browser; no auth tokens are put in localStorage
or sessionStorage. If your CSRF cookie is lost, log in again before retrying logout.

### Frontend and browser tests

From `frontend/`, run `npm ci`, `npm run lint`, `npm run type-check`, `npm run test`, and `npm run build`.
Vitest runs the API/cookie unit tests; the Playwright lifecycle uses real APIs, PostgreSQL, and browser cookies.
Install the browser once from `frontend/`:

```sh
npx playwright install chromium
# On a Linux host needing browser OS libraries:
# npx playwright install --with-deps chromium
```

With Docker running and ports 3000, 8000 and 5432 free, run from the repository root:

```sh
python scripts/run_auth_e2e.py
```

The runner creates a unique `ss-r5-e2e-<random>` project, verifies that it has no existing resources,
builds the images, starts the fresh database/migration/backend/frontend stack, runs the HTTP smoke check,
then executes `npm run test:e2e` in `frontend/`. It removes only that disposable project's containers,
network and volumes in a finally block, including on test failure. Normal development data is untouched.
Do not run this test against an unknown developer database. It creates unique accounts rather than
using persistent seeded credentials. Never set its safety flags for a valuable environment.

For machines with Chrome already installed when a managed browser download is unavailable, set
`PLAYWRIGHT_CHANNEL=chrome` before invoking the same runner. PowerShell:
`$env:PLAYWRIGHT_CHANNEL='chrome'`; Unix: `export PLAYWRIGHT_CHANNEL=chrome`.
CI installs managed Chromium. Both paths run the same Playwright test without mocking authentication.

The direct `npm run test:e2e` command requires `ALLOW_DISPOSABLE_E2E=1` and an `E2E_COMPOSE_PROJECT`
matching `ss-r5-e2e-*`; its setup verifies the named healthy Compose frontend is actually bound to
127.0.0.1:3000. The runner sets these variables automatically. CI safely supplies its unique job project
and extends the existing Compose smoke job, sharing the same stack rather than building another one.
Browser traces are disabled to avoid recording raw session credentials. Test screenshots show UI only;
all test artifacts are ignored by Git and Docker build contexts.

### Owner's manual check (not performed by automation on your behalf)

1. Open http://localhost:3000.
2. Register.
3. Confirm signed-in state.
4. Refresh.
5. Confirm still signed in.
6. Open a second tab.
7. Confirm signed in there.
8. Logout.
9. Refresh both tabs.
10. Confirm both are unauthenticated.
11. Login with the wrong password.
12. Confirm the generic error.
13. Login with the correct password.
14. Confirm signed-in state.


## Application Profile (Phase 6B)

Login and open the Application Profile link, or visit `/profile`. Legal first/last names are required;
preferred/middle names, phone, address and LinkedIn/GitHub/portfolio links are optional. Street lines
share the existing multiline street-address field. Enter an explicit two-letter country code.
Save, refresh to check persistence, edit one field, or clear an optional field and save again.

`GET /api/v1/profile` returns the current user's facts or null before first save. `PATCH` sends only
changed fields; omitted fields stay unchanged and explicit null clears an optional field. Updates
read the current `ss_csrf` cookie using the R5 helper and send `X-CSRF-Token`. Ownership is resolved
from the server session. These Application Facts never set Career Preferences or Resume Evidence.

Run `python -m alembic -c backend/alembic.ini upgrade head` before starting the backend. The narrow
`b61f0a2c9d34` migration makes five optional contact/address columns nullable and preserves existing
values. See [model decisions and semantics](docs/phase6b-profile.md).
Focused PostgreSQL tests: `python -m pytest backend/tests/test_profile.py backend/tests/test_profile_migration.py -q`
using the disposable test environment described above. The existing CI discovers these tests automatically.

R5 is owner-accepted with a documented waiver: its corrected local Playwright lifecycle was not rerun
because Docker Desktop was unstable. Phase 6B does not reopen that verification or remove CI E2E.
Education and its GPA precision prerequisite are implemented in Phase 6C below.


## Education (Phase 6C)

Apply `python -m alembic -c backend/alembic.ini upgrade head`, start the native backend/frontend as
above, login, and open the Education link or `/education`. An Application Profile row is not required.
Add one or more institutions with the approved degree/study-year choices, actual start date and
expected graduation month/year. Edit, save and refresh to verify persistence. Delete asks for explicit
confirmation and removes only that record.

GPA is entered as its original value / scale (for example 4.20 / 4.33 or 100.00 / 100.00). No conversion
or scale inference occurs. Both fields are optional together; enabling inclusion on applications
requires both. To clear GPA, clear both and disable inclusion. GPA supports at most two decimal places.

Primary is an explicit checkbox, false by default. Selecting it demotes the previous primary atomically;
zero primary records is valid. Deleting a primary does not guess a replacement. These are Application
Facts, never Career Preferences or Resume Evidence.

The API uses `/api/v1/profile/education` and `/{id}`. Ownership comes from the server session; every
mutation reads the current CSRF cookie with the existing helper. PATCH preserves omitted fields and
validates the complete resulting record. Success responses use no-store.

Migration `c72e4b9d103f` widens gpa_value to NUMERIC(5,2), adds GPA/date constraints and primary uniqueness,
and changes the primary default to false. Invalid existing facts or duplicate primary rows block upgrade
without repair. Downgrade deliberately refuses values above 99.99. See docs/database.md for details.
Focused tests (disposable PostgreSQL environment above):
`python -m pytest backend/tests/test_education.py backend/tests/test_education_migration.py -q`.
The existing CI discovers Education tests; the accepted R5 browser suite and waiver are unchanged.


## Employment (Phase 6D)

Apply `python -m alembic -c backend/alembic.ini upgrade head`, run the native stack as above, login and
open `/employment` through the Employment link. Add an employer, title and start date. A completed
role requires an end date. A current role can omit it or retain a known/contracted end date; toggling
Currently employed never erases that date. End date must not precede start date.

Location is free-text historical work location, not a desired job location. Description is factual
text; no skills or resume evidence are extracted. Neither ApplicationProfile nor Education is a
prerequisite. Edit sends changed fields, with optional null clearing and server validation of the
complete resulting record. Delete requires explicit confirmation. Refresh shows persisted facts.

The nested `/api/v1/profile/employment` API uses session ownership, current-cookie CSRF on all mutations,
and no-store success responses. Mutation commits belong to the service; PATCH/DELETE lock only the
owned employment row, not the User aggregate. The new `d83f5ca21460` migration adds only chronological
date protection, refuses reversed legacy dates without repair, and downgrades by dropping that check.

Focused PostgreSQL tests: `python -m pytest backend/tests/test_employment.py backend/tests/test_employment_migration.py -q`
using the disposable test settings above. Existing CI automatically includes these tests and the new
Vitest cases. Prior Profile/Education behavior and R5's documented waiver remain unchanged.


## Work Authorization (Phase 6E)

Apply `python -m alembic -c backend/alembic.ini upgrade head`, start the native stack as above, login and open `/work-authorization`. Add countries, explicitly choose status and both sponsorship answers, edit, clear notes and confirm deletion. Refresh reloads persisted facts.

Work Authorization is one-to-many per User, with exactly one record per user/country and no ApplicationProfile prerequisite. Country identifies the authorization jurisdiction, not residence, nationality or desired job location. API normalization trims and uppercases exactly two ASCII letters; neither API nor database claims ISO membership validation.

The structured statuses are CITIZEN, PERMANENT_RESIDENT, STUDENT_WORK_AUTHORIZATION, TEMPORARY_WORK_AUTHORIZATION, OTHER, STUDENT_VISA_CPT_OPT and WORK_VISA. Phase 6E adds the two generic authorization choices while retaining every baseline value unchanged. CPT/OPT is explicitly a US-specific legacy label; WORK_VISA is a retained legacy label. These are user-selected categories, not determinations of legal eligibility. No legacy facts are mapped or reinterpreted, and no legal equivalence is asserted.

Current and future sponsorship are independent explicit booleans. Status never sets sponsorship, and sponsorship never sets status. Notes are optional factual text, trimmed, limited to 255 characters; blank/null clears. Do not enter government document numbers. Nothing is inferred from notes, location, profile, education, employment or external sources. No job compatibility is computed.

last_confirmed_at is server-managed UTC: set on POST and refreshed on successful PATCH containing at least one editable fact, even if its value is unchanged. GET and empty PATCH preserve the timestamp. The UI sends only changed facts, so an unchanged form closes without reconfirming. Clients cannot supply IDs, ownership or timestamps.

The nested `/api/v1/profile/work-authorizations` API uses session ownership, current-cookie CSRF and no-store success responses. Lists sort by country_code then id. Duplicate creation or country edits return controlled 409. PATCH/DELETE lock only the owned record; PostgreSQL uniqueness handles concurrent writes.

Focused PostgreSQL tests: `python -m pytest backend/tests/test_work_authorization.py backend/tests/test_work_authorization_migration.py -q`, using the explicit disposable test settings above. Migration `e94a6db32571` follows `d83f5ca21460`, adds country/status checks and never repairs legacy facts. Phase 6F remains deferred.


## Career Preferences (Phase 6F)

Apply `python -m alembic -c backend/alembic.ini upgrade head`, start the native stack as above, login and open `/preferences`. Select desired options, add explicit Other values, save, then refresh. Saving replaces all previous selections with the current complete form.

Career Preferences are explicit desired choices, separate from Profile, Education, Employment, Work Authorization and resume evidence. Technology interests use Skill/UserPreferredSkill only and do not create UserSkill or capability claims. No preferences are inferred.

GET `/api/v1/preferences` is authenticated, returns a deterministic complete selection object (empty arrays when unsaved), and creates no row. PUT on the same route is authenticated, requires the current session CSRF token, and replaces the full aggregate: role_ids, industry_ids, location_ids, company_ids, skill_ids, work_modes, employment_types and custom_values. Omitted arrays mean empty and remove previous selections. Success responses use no-store; body/query user_id is rejected. IDs are UUIDs; duplicate canonical IDs and structured choices are deduplicated and sorted. Unknown IDs return controlled 422 before any replacement.

Work modes: ON_SITE, HYBRID, REMOTE. Employment types: INTERNSHIP, CO_OP, NEW_GRAD, PART_TIME. Custom entries have preference_type ROLE/INDUSTRY/LOCATION/COMPANY/SKILL and display value (nonblank, maximum 150 characters). Display text is preserved exactly. Normalized uniqueness uses whitespace collapse/trim plus Unicode casefold, with a maximum normalized length of 150. Duplicate normalized values within a type are rejected; matching values in different types are allowed. Custom entries never become canonical taxonomy entries, even when their labels match.

The service locks the existing User row for aggregate replacement, validates all canonical IDs (with key-share locks against concurrent deletion), then updates the root, joins and custom values in one transaction and commits once. Identical PUT preserves existing root/custom row IDs and timestamps. GET takes a shared User-row lock for a coherent multi-table read. Repository methods never commit. Different users are independent.

Catalog endpoints are authenticated read-only GETs and require no CSRF. Roles support q and active (default true; false returns inactive roles). Skills support q/category and return active skills. Companies support q. Locations support country_code (case-insensitive two-letter filter) and q over city/state-province. Industries have no filters. Search is literal case-insensitive substring, not wildcard input. Names sort case-insensitively then by ID; locations sort country, case-insensitive city, state/province, ID. No catalog mutations are exposed. Existing inactive canonical IDs remain valid preferences; selected items missing from active catalogs stay visible as removable saved IDs in the form.

The `/preferences` form loads catalogs from these APIs, supports multiple selections and explicit Other entries, and saves one complete PUT. New installations have no seeded canonical catalog: empty catalog messaging and custom values are supported. Browser verification fixtures are disposable and are never seeded by migrations. Phase 6G and matching remain deferred.

Focused tests: `python -m pytest backend/tests/test_preferences.py backend/tests/test_preferences_migration.py -q`, using the existing explicit disposable PostgreSQL test settings.


## Onboarding Review (Phase 6G)

From the signed-in home or any data page, open `/onboarding/review`. It reads the existing saved Profile, Education, Employment, Work Authorization and Career Preferences APIs, with catalog labels. It never writes preference selections or converts technology interests into skill claims. Empty sections are shown explicitly; unavailable catalog labels retain their saved IDs. A failed load must be retried before completion is enabled.

Each section links to its existing Edit page. Save there, then use Return to onboarding review. Navigating or refreshing loads saved backend values; unsaved form edits are not auto-saved. No new fields or summary endpoint were added.

The accepted baseline has no onboarding completion flag, wizard state or completion API. Complete onboarding explicitly finishes this review, checks the current session and returns to the existing signed-in home (`/`). It makes no data mutation, writes no browser completion marker, and does not persist a completion timestamp or gate future access. Repeated clicks are guarded. The review remains available to revisit. No backend, database, migration, dependency or contract changes were needed.

Focused tests: from frontend, `npx vitest run lib/onboarding/review.test.ts lib/onboarding/review-render.test.ts`. Rendering tests reuse React's existing server renderer; the Vitest JSX setting enables those tests without adding dependencies. Later phases remain unimplemented.

## Candidate Profile (Phase 8C)

Open **Candidate Profile** from the signed-in Home page or visit `/candidate`. This is a read-only,
source-aware view over your saved application facts, projects, preferences, confirmed skills, and
version-scoped resume evidence. It does not create a profile row, parse a resume, or change any saved data.

Each catalog skill keeps every source: **Added by you** means an explicit confirmed `UserSkill`; **Found in
resume** cites the exact resume title and version; **Used in project** cites the saved project. A detected
resume reference or project technology never becomes a confirmed skill automatically. Custom skill text is
grouped only by its existing normalized value and retains the same source labels. Resume evidence remains
separate from confirmed facts and does not expose extracted text or managed file data.

`GET /api/v1/profile/candidate` is authenticated, derives ownership exclusively from the session, rejects a
client `user_id`, performs no writes, and returns `Cache-Control: no-store`. It is covered by the generated
OpenAPI contract and needs no CSRF header because it is read-only.

## Jobs (Phases 9–11)

Signed-in users can open **Jobs** from Home or visit `/jobs`. The page searches active shared job records by
keyword, location, company, skill requirement, employment type, and work mode; it keeps the committed search
and page in the URL so a refresh preserves the discovery view. It loads the selected record's plain-text
description, locations, and explicit skill, education, and eligibility requirements. Requirements describe the
posting only; they are never compared with, copied into, or used to change Candidate Profile, skills, resumes,
education, employment, or work authorization.

`GET /api/v1/jobs` and `GET /api/v1/jobs/{id}` are authenticated, read-only endpoints with no CSRF header.
The list accepts bounded `keyword` (or `query`), `location`, `company`, `requirement`, `employment_type`
(or `type`), `work_mode`, `page`, `page_size`, and fixed `sort` parameters. It returns an `items`, `page`,
`page_size`, `total`, and `total_pages` envelope. Searches are literal case-insensitive catalog queries, and
the fixed sort choices are newest, oldest, title ascending, and title descending. Raw ingestion snapshots,
source adapter identifiers, external source IDs, candidate data, applications, evaluation data, matching, and
scores are not exposed. Jobs are shared records, not user-owned data; unknown, repeated, and client ownership
query input is rejected, and inactive and unknown detail IDs both return the same safe 404. Responses are
`Cache-Control: no-store`.

Phase 10 creates and updates shared job records only through the internal source-adapter, normalizer, service,
and repository pipeline. It reuses each source record and preserves its original `source_url`; canonical
whitelisted normalized facts are snapshotted and hashed internally. Repeating an unchanged successful fetch
does not add a snapshot or replace facts, but it advances the job's `last_verified_at` timestamp. There is no
public ingestion, import, or job mutation route, and no Jobs response exposes source provenance.

## Live job ingestion (Phase 18)

The manual importer supports the public Greenhouse Job Board API, Lever Postings API, Ashby Job Postings API,
SmartRecruiters Posting API, and bounded public RSS/Atom career feeds. Configure one or more public sources with
`LIVE_JOB_SOURCES_JSON`; configuration is disabled by default and contains no credentials. Each entry has a safe
source `key`, a `family`, an enabled flag, the provider's public board identifier or feed URL, a configured
`company`, and a configured catalog `role`. Use `Unspecified` for a role that is not known from the source
configuration rather than inferring one from a title or description.

```json
[
  {
    "key": "greenhouse.example",
    "family": "greenhouse",
    "board_token": "example",
    "company": "Example",
    "role": "Unspecified",
    "enabled": true,
    "max_postings": 100
  },
  {
    "key": "lever.example",
    "family": "lever",
    "site": "example",
    "company": "Example",
    "role": "Unspecified",
    "enabled": true
  },
  {
    "key": "ashby.example",
    "family": "ashby",
    "job_board": "Example",
    "company": "Example",
    "role": "Unspecified",
    "enabled": true
  },
  {
    "key": "smartrecruiters.example",
    "family": "smartrecruiters",
    "company_identifier": "example",
    "company": "Example",
    "role": "Unspecified",
    "enabled": true,
    "max_postings": 50
  },
  {
    "key": "rss.example",
    "family": "rss",
    "feed_url": "https://careers.example/jobs.xml",
    "allowed_job_hosts": ["jobs.example", "apply.example"],
    "company": "Example",
    "role": "Unspecified",
    "enabled": true
  }
]
```

Run `python -m backend.app.commands.ingest_live --all`, select one source with
`--source greenhouse.example`, or select an adapter family with `--family greenhouse`. The command fetches before
opening database transactions and gives every valid posting its own existing ingestion transaction. It preserves
the provider external ID, source URL, the best known official application URL, published/update timestamps when
the provider exposes them, and the database fetch timestamp. A malformed item is skipped without replacing a
previous valid job, and no user, resume, application, or candidate record is changed.

## Continuous live collection (Phase 19)

The Compose stack starts a separate `collector` process after migrations complete. It uses the same configured
public adapters and the existing transactional ingestion service; it never makes a job closed merely because a
fetch fails or returns no records. Configure the same `LIVE_JOB_SOURCES_JSON` array as Phase 18. Each source can
optionally set a safe `poll_interval_seconds` (5 minutes to 24 hours) and `request_timeout_seconds` (up to 60
seconds). Defaults are source-aware: Lever polls every 10 minutes; Greenhouse, Ashby, and SmartRecruiters every
15 minutes; RSS/Atom feeds every 30 minutes.

Each configured source has durable health and scheduling state: next poll, attempt/success/completion times,
bounded failure count, error category/status, last result count, and public ETag/Last-Modified validators where
the provider actually supplies them. The collector performs conditional requests only after receiving one of
those validators, treats a 304 as a healthy unchanged source, applies deterministic jitter, and uses bounded
exponential backoff. A valid `Retry-After` takes precedence for rate limits. Source workers run independently
with `LIVE_COLLECTOR_CONCURRENCY` bounded to 3 by default.

Use `python -m backend.app.commands.collect_live once --all` for one forced diagnostic cycle,
`python -m backend.app.commands.collect_live run` for the continuous process, and
`python -m backend.app.commands.collect_live health` for a compact source-health view. Disabled boards are
recorded as disabled and never fetched. A source that unexpectedly becomes empty or rejects all examined
records is marked degraded; existing jobs remain intact.

## Fast new-job alerts (Phase 23)

Saved Searches begin with alerts Off. Enabling Instant, Hourly digest, or Daily digest records a durable UTC
activation watermark, so jobs first discovered before activation do not backfill. Changing the structured
criteria or re-enabling a search establishes a new watermark for the same reason. Alert matching reuses the
Jobs feed's structured predicate and stores at most one durable event for each user, Saved Search, and canonical
job. The private inbox resolves the current canonical Apply URL when it is read.

Compose starts `alert-worker` after migrations. It reconciles bounded post-watermark slices and delivers due
in-app events every 30 seconds; `python -m backend.app.commands.process_job_alerts once` runs one recovery and
delivery cycle for an operator. Instant events are made available in the new canonical-job transaction, while
hourly and daily digest events use the next UTC hour and UTC midnight respectively. Pending events are suppressed
if the job is closed or hidden before delivery, and delivery retries use bounded backoff.

## Canonical jobs and lifecycle (Phase 20)

NormalizedJob remains the user-visible canonical job record. Each supported source identity now has one
JobSourceObservation row that retains its current normalized facts, freshness timestamps, authority class,
safe source/application URLs, and source-specific absence state; immutable raw snapshots remain separate.
The public Jobs API continues to expose one clean card, never source IDs, raw payloads, or adapter internals.

Cross-source merging is deliberately narrow. StudentSuccessful links postings only when a current official
application URL, a current official source URL, or the exact combination of company, normalized title, and
non-empty normalized location set agrees. Similar titles, description similarity, unknown locations, and fuzzy or
model-based matching never merge jobs. Multi-location postings preserve their source location set, and different
locations remain separate unless an authoritative URL proves they are the same opening.

Source authority is adapter metadata, not a Greenhouse/Lever/Ashby special case. Official company and ATS
observations outrank structured feeds, aggregators, and unknown sources. Canonical fields use the best available
explicit source fact without replacing known authoritative values with unknown data. The Apply destination prefers
a direct official form, then an official ATS/company page, then lower-authority source URLs. Source provenance for
the selected facts and link remains internal.

first_seen_at is immutable discovery history; last_seen_at and last_verified_at advance only from successful
source observations; source-specific source_updated_at remains provenance. NEW is a presentation state derived
from JOB_NEW_WINDOW_HOURS (72 by default). A clean, complete successful source listing that omits a previously
observed posting first makes it STALE; only every supporting observation missing across
JOB_CLOSE_AFTER_SUCCESSFUL_ABSENCES clean listings (2 by default), or an explicit authoritative closure, marks it
CLOSED. A timeout, fetch failure, rate limit, incomplete listing, malformed provider data, or a failed collector
does not change a job to closed. Closed jobs are omitted from the normal Jobs list; stale jobs remain visible with
their last verification time.

## Source coverage expansion (Phase 21)

Additional boards for every supported ATS family are configuration-only: adding a Greenhouse token, Lever site,
Ashby job board, SmartRecruiters company identifier, or allowed public RSS/Atom feed does not change scheduler or
canonicalization code. SmartRecruiters uses bounded offset pagination and a maximum of 50 postings per cycle.
RSS/Atom sources fetch only their configured HTTPS feed; they never crawl links, execute scripts, follow redirects,
or leave the configured public job-host allowlist.

Each source can declare `polling_tier` as `high`, `normal`, or `low` when it does not set an explicit interval.
The deterministic policy uses half, base, or double the source-family interval, bounded to five minutes through one
day. Operators choose the tier after reviewing the collector's durable totals for observed jobs, newly contributed
canonical jobs, duplicate contributions, internship/co-op contributions, official Apply destinations, failures,
and last new canonical job. `source_authority` remains restricted to the existing generic authority classes, so
canonical field resolution and best-Apply selection continue to preserve every lower-authority observation.
