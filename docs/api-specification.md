# StudentSuccessful — REST API Design Specification (Phase 4)

**Document Version:** 1.0 (Baseline Specification)  
**Phase:** SDLC Phase 4 — REST API Design  
**Status:** Under Review (Awaiting Mentee Approval)  
**Depends On:** Phase 3.1 Database Design Baseline v1.2  

---

## 1. Architectural Standards & Design Invariants

All endpoints conform to the following standards:
1. **Base URL & Versioning:** All product endpoints are prefixed with `/api/v1/`. Health checks (`/health/live`, `/health/ready`) remain unversioned.
2. **Response Envelopes:**
   - Single-resource: `{"data": { ... }}`
   - Collections: `{"data": [ ... ], "meta": {"page": 1, "page_size": 25, "total": 132, "total_pages": 6}}`
3. **RFC 9457 Problem Details for Errors:** Standard error content type `application/problem+json` containing `type`, `title`, `status`, `detail`, `instance`, `code` (stable machine enum), and optional `errors` array.
4. **Authentication & Session Cookies:**
   - Server-managed sessions via `__Host-ss_session` cookie (`HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`).
   - Token hashes are stored in the DB (`user_sessions`). Tokens are never kept in `localStorage`.
5. **CSRF Protection:** Authenticated state-changing requests require `X-CSRF-Token`, validated against the active session. Registration/login instead use explicit frontend Origin validation before a session exists. See the R3 auth contract below.
6. **Strict Ownership & No Client-Supplied `user_id`:** The server derives `user_id` strictly from the validated session. Clients never supply `user_id`.
7. **Strict Pydantic Validation:** All request payloads use `extra = "forbid"` to reject unauthorized or extraneous fields.
8. **Deferred comparison features:** Candidate fit, resume-job alignment, scoring, recommendations, and
   resume evaluation are not part of the implemented API.

---

## 2. API Endpoint Matrix

### 2.1 Authentication & Account Management
- `POST /api/v1/auth/register` (Email, password $\rightarrow$ establishes session)
- `POST /api/v1/auth/login` (Generic `INVALID_CREDENTIALS` error)
- `POST /api/v1/auth/logout` (Requires active session + valid CSRF header; revokes the session and clears both cookies)
- `GET /api/v1/auth/me` (Returns authenticated user summary)
- `GET /api/v1/account/export` (Returns all user-owned data as JSON)
- `DELETE /api/v1/account` (Cascades user-owned data deletion; requires recent re-auth)
- `GET /api/v1/onboarding/status` (Section completion flags)

#### R3 authentication/session contract

- Registration (`201`) and login (`200`) generate a new independent pair of 256-bit random credentials. PostgreSQL stores only their SHA-256 digests.
- The session credential is returned only through a host-only session cookie: `__Host-ss_session` in production, `ss_session` for insecure local HTTP. It is HttpOnly, SameSite=Lax, Path=/, and Secure in production, with no Domain attribute. Production misconfiguration fails validation.
- The matching raw CSRF token is set in host-only `ss_csrf`: SameSite=Lax, Path=/, Secure in production, **not** HttpOnly. Both cookies have the session's configured lifetime. The existing response `{ "user": {...}, "csrf_token": "..." }` is retained; the returned CSRF value is identical to the cookie. Browser mutation code should read the current cookie immediately before sending `X-CSRF-Token`.
- `GET /api/v1/auth/csrf` is removed from V1 and returns 404. There is no rotation endpoint. If the CSRF cookie is lost, log in again to establish a new pair; hashes cannot recover a lost raw token.
- One session has one CSRF token, shared by its browser tabs. Ordinary `/auth/me` reads neither rotate the token nor write `last_seen_at`, commit, or extend `expires_at`. Expiration is absolute; no idle-expiry policy exists.
- Logout validates the session first (401 for missing/tampered/expired/revoked/inactive-user sessions), then the header against that session's CSRF digest (403 `CSRF_TOKEN_INVALID` for missing/wrong values). A successful logout commits revocation and expires both cookies using the same names, Path=/ and security attributes. Other sessions remain valid. Tokens from different sessions cannot be mixed.
- Registration and login require exactly one `Origin` matching configured `FRONTEND_ORIGIN` in production. Missing, `null`, duplicate, and foreign origins return 403 `AUTH_ORIGIN_REJECTED` before opening the Unit of Work. Non-production CLI/tests may omit Origin, but a supplied foreign origin is still rejected. CORS trusts only the configured origin, without wildcard or implicit localhost additions.
- For a same-origin Next.js rewrite, configure the browser-facing frontend origin (for example `https://students.example`), preserve the browser's Origin header, and do not substitute the backend's internal Host or trust forwarded headers as authorization. Browser scripts cannot choose a different Origin header; this blocks cross-site login/registration submissions before they can replace a browser's session.
- All responses under `/api/v1/auth/`, including handled failures and validation errors, carry `Cache-Control: no-store`. This policy does not change unrelated API caching.
- Existing auth success shapes and application/json error bodies remain unchanged. This milestone documents auth 401/403/409 responses in OpenAPI; a global envelope/Problem Details redesign remains deferred. Generic invalid-login errors remain 401 `INVALID_CREDENTIALS`.

### 2.2 Profile, Education, Employment & Work Authorization
**Implemented in Phase 6B:**
- `GET /api/v1/profile`: authenticated user's contact/identity facts, or JSON `null` before first save; never creates a row.
- `PATCH /api/v1/profile`: creates with legal first/last names or updates only supplied fields. Optional null/blank values clear; omissions preserve. Legal first/last names cannot be cleared.
- Fields: `legal_first_name`, `legal_middle_name`, `legal_last_name`, `preferred_name`, `phone_number`, `address_street` (multiline), `address_city`, `address_state_province`, `address_postal_code`, `address_country_code` (explicit two-letter code), `linkedin_url`, `github_url`, `portfolio_url`.
- Session-derived ownership only; no client user ID or editable account email. PATCH requires the current `ss_csrf` cookie value in `X-CSRF-Token` using the existing CSRF helper. Unauthenticated requests return 401, invalid CSRF 403, invalid fields 422 through FastAPI validation.
- Success bodies are flat profile objects (GET may return null), with `Cache-Control: no-store`; no global envelope redesign. Links accept absolute http/https only, are never fetched, and do not infer facts. Application Facts do not set Career Preferences or Resume Evidence.
- [Full model and migration decisions](phase6b-profile.md).

**Implemented in Phase 6C:**
- `GET /api/v1/profile/education` (200 array, ordered by created_at then id).
- `POST /api/v1/profile/education` (201 EducationRead).
- `PATCH /api/v1/profile/education/{id}` (200 EducationRead, final-state partial validation).
- `DELETE /api/v1/profile/education/{id}` (204, empty body).
- Records belong directly to the authenticated user; no ApplicationProfile prerequisite. Request user_id is forbidden in bodies and query parameters. PATCH/DELETE query by record ID plus owner ID; missing and unowned records return the same safe 404 code/detail.
- Every mutation requires existing session-bound CSRF. Success responses are no-store. Flat objects/arrays follow current implemented endpoints; the proposed global envelope redesign remains deferred.
- Required facts: institution_name (255), degree_level, major (150), study_year, start_date, expected_grad_month (1–12), expected_grad_year (2000–2100). Optional minor (150). Degree choices: BS, BA, MS, PHD, ASSOCIATES, OTHER. Study choices: YEAR_1, YEAR_2, YEAR_3, YEAR_4, YEAR_5_PLUS, GRADUATE, OTHER.
- GPA value and scale are a complete optional Decimal pair with NUMERIC(5,2) precision. Responses serialize decimal strings; the browser submits strings, never converts scales. Value is nonnegative, scale positive, value ≤ scale; excess precision is rejected. gpa_include_on_apps defaults false and requires a pair when true.
- PATCH merges supplied fields with stored facts before validating GPA/disclosure/date ordering. Explicit optional null clears; omissions preserve. Clear GPA with both nulls and gpa_include_on_apps=false if it was enabled.
- is_primary defaults false. Explicit selection demotes the previous primary in the same owner-serialized transaction. Zero primaries is allowed; delete does not infer a replacement.

**Implemented in Phase 6D:**
- `GET /api/v1/profile/employment`: 200 array, ordered by created_at then id, current user's records only.
- `POST /api/v1/profile/employment`: 201 EmploymentRead; employer_name (nonblank, max 255), job_title (nonblank, max 150), start_date required; currently_employed defaults false. Optional location (max 150), end_date and description.
- `PATCH /api/v1/profile/employment/{id}`: 200 EmploymentRead. Merge supplied fields with the owned locked row, then validate before assignment. Omitted fields survive; optional null clears. Changing currently_employed does not automatically change end_date.
- `DELETE /api/v1/profile/employment/{id}`: 204 empty body.
- Current=false requires an end date; current=true permits both absent and present end dates. Any present end date must be >= start date. Invalid final state returns FastAPI 422. Description preserves nonblank content and line breaks; blank location/description normalize to null.
- Owner comes from the authenticated session; no ApplicationProfile prerequisite. Body/query user_id is rejected. Missing and unowned record IDs share safe 404 code/detail. POST/PATCH/DELETE reuse require_csrf and the client reads the current cookie immediately before each mutation.
- Success responses use no-store and existing flat object/array shapes. Employment location and description are submitted facts, never preferences, taxonomy links or inferred resume evidence.

**Work Authorization (implemented Phase 6E):**
- `GET /api/v1/profile/work-authorizations`: 200 owned array, ordered country_code then id.
- `POST /api/v1/profile/work-authorizations`: 201 WorkAuthorizationRead. Country/status required; current/future sponsorship boolean defaults remain false at the API, with explicit choices required by the form. Optional notes (255).
- `PATCH /api/v1/profile/work-authorizations/{id}`: 200 merged, validated owned record; omitted facts preserved, only optional notes may clear. Empty object returns unchanged record.
- `DELETE /api/v1/profile/work-authorizations/{id}`: 204 empty body.
- Body/query user_id is rejected; owner is session-derived. Required fields reject null. Read-only timestamps and IDs reject client input. Success responses use no-store. Mutations reuse require_csrf. Missing/unowned IDs share 404 WORK_AUTHORIZATION_NOT_FOUND. Expected unique-constraint collisions return 409 WORK_AUTHORIZATION_ALREADY_EXISTS; other validation uses 422.
- Repository never commits; service commits once per mutation (empty PATCH performs no mutation/commit). PATCH/DELETE lock the specific owned row; no User lock. PostgreSQL unique(user_id,country_code) is authoritative under concurrency.

Work Authorization is one-to-many per User, with exactly one record per user/country and no ApplicationProfile prerequisite. Country identifies the authorization jurisdiction, not residence, nationality or desired job location. API normalization trims and uppercases exactly two ASCII letters; neither API nor database claims ISO membership validation.

The structured statuses are CITIZEN, PERMANENT_RESIDENT, STUDENT_WORK_AUTHORIZATION, TEMPORARY_WORK_AUTHORIZATION, OTHER, STUDENT_VISA_CPT_OPT and WORK_VISA. Phase 6E adds the two generic authorization choices while retaining every baseline value unchanged. CPT/OPT is explicitly a US-specific legacy label; WORK_VISA is a retained legacy label. These are user-selected categories, not determinations of legal eligibility. No legacy facts are mapped or reinterpreted, and no legal equivalence is asserted.

Current and future sponsorship are independent explicit booleans. Status never sets sponsorship, and sponsorship never sets status. Notes are optional factual text, trimmed, limited to 255 characters; blank/null clears. Do not enter government document numbers. Nothing is inferred from notes, location, profile, education, employment or external sources. No job compatibility is computed.

last_confirmed_at is server-managed UTC: set on POST and refreshed on successful PATCH containing at least one editable fact, even if its value is unchanged. GET and empty PATCH preserve the timestamp. The UI sends only changed facts, so an unchanged form closes without reconfirming. Clients cannot supply IDs, ownership or timestamps.

**Deferred endpoints (not implemented by Phase 6E):**
- `GET /api/v1/profile/application-answers` & `POST /api/v1/profile/application-answers`
- `PATCH /api/v1/profile/application-answers/{id}` & `DELETE /api/v1/profile/application-answers/{id}`

### 2.3 Taxonomies & Preferences (implemented Phase 6F)
- `GET /api/v1/catalog/roles` (`?q=...&active=true`)
- `GET /api/v1/catalog/skills` (`?q=...&category=...`)
- `GET /api/v1/catalog/industries`
- `GET /api/v1/catalog/companies` (`?q=...`)
- `GET /api/v1/catalog/locations` (`?country_code=...&q=...`)
- `GET /api/v1/preferences`
- `PUT /api/v1/preferences` (Idempotent full aggregate replacement; canonical ID arrays and separate typed custom entries)

Career Preferences are explicit desired choices, separate from Profile, Education, Employment, Work Authorization and resume evidence. Technology interests use Skill/UserPreferredSkill only and do not create UserSkill or capability claims. No preferences are inferred.

GET `/api/v1/preferences` is authenticated, returns a deterministic complete selection object (empty arrays when unsaved), and creates no row. PUT on the same route is authenticated, requires the current session CSRF token, and replaces the full aggregate: role_ids, industry_ids, location_ids, company_ids, skill_ids, work_modes, employment_types and custom_values. Omitted arrays mean empty and remove previous selections. Success responses use no-store; body/query user_id is rejected. IDs are UUIDs; duplicate canonical IDs and structured choices are deduplicated and sorted. Unknown IDs return controlled 422 before any replacement.

Work modes: ON_SITE, HYBRID, REMOTE. Employment types: INTERNSHIP, CO_OP, NEW_GRAD, PART_TIME. Custom entries have preference_type ROLE/INDUSTRY/LOCATION/COMPANY/SKILL and display value (nonblank, maximum 150 characters). Display text is preserved exactly. Normalized uniqueness uses whitespace collapse/trim plus Unicode casefold, with a maximum normalized length of 150. Duplicate normalized values within a type are rejected; matching values in different types are allowed. Custom entries never become canonical taxonomy entries, even when their labels match.

The service locks the existing User row for aggregate replacement, validates all canonical IDs (with key-share locks against concurrent deletion), then updates the root, joins and custom values in one transaction and commits once. Identical PUT preserves existing root/custom row IDs and timestamps. GET takes a shared User-row lock for a coherent multi-table read. Repository methods never commit. Different users are independent.

Catalog endpoints are authenticated read-only GETs and require no CSRF. Roles support q and active (default true; false returns inactive roles). Skills support q/category and return active skills. Companies support q. Locations support country_code (case-insensitive two-letter filter) and q over city/state-province. Industries have no filters. Search is literal case-insensitive substring, not wildcard input. Names sort case-insensitively then by ID; locations sort country, case-insensitive city, state/province, ID. No catalog mutations are exposed. Existing inactive canonical IDs remain valid preferences; selected items missing from active catalogs stay visible as removable saved IDs in the form.

The `/preferences` form loads catalogs from these APIs, supports multiple selections and explicit Other entries, and saves one complete PUT. New installations have no seeded canonical catalog: empty catalog messaging and custom values are supported. Browser verification fixtures are disposable and are never seeded by migrations. Phase 6G and matching remain deferred.

### 2.4 Resumes & Deterministic Resume Evidence

**Implemented through Phase 8B:**

- `GET /api/v1/resumes` & `POST /api/v1/resumes` (Logical document families)
- `GET /api/v1/resumes/{id}`, `PATCH /api/v1/resumes/{id}`, `DELETE /api/v1/resumes/{id}`
- `GET /api/v1/resumes/{id}/versions`
- `POST /api/v1/resumes/{id}/versions` (Multipart upload, 5MB limit, layered validation, compensating deletion)
- `PUT /api/v1/resumes/{id}/primary-version` (Sets primary active version)
- `GET /api/v1/resume-versions/{id}`, `DELETE /api/v1/resume-versions/{id}`
- `GET /api/v1/resume-versions/{id}/file` (Authenticated streaming)
- `POST /api/v1/resume-versions/{id}/parse` (CSRF-protected, explicit local PDF/DOCX extraction)
- `GET /api/v1/resume-versions/{id}/evidence` (Version-scoped parser evidence)
- `GET /api/v1/resume-versions/{id}/extracted-text` (Private normalized text for the owner)

All three evidence routes derive ownership from the session, return `404` for
missing or unowned versions, and use `Cache-Control: no-store`. Parsing never
runs on GET. The mutation either atomically replaces one version's complete
evidence set and marks `PARSED_SUCCESS`, or marks `PARSE_FAILED` while retaining
any earlier successful raw text and evidence for retry. `ResumeEvidenceSkill`
is parser evidence only; it does not confirm or create `UserSkill` records.

**Deferred, not implemented by Phase 8C:**

- `PATCH /api/v1/resume-evidence-items/{id}`
- Candidate fit, evaluation, matching, scoring, rewriting, and application routes

### 2.5 Candidate Profile (implemented Phase 8C)

- `GET /api/v1/profile/candidate` returns one authenticated user's derived Candidate Profile.
- Ownership is session-derived; the endpoint accepts no body or client `user_id` and rejects a `user_id` query
  parameter. It is read-only, requires no CSRF header, and all success, authentication, and validation responses
  carry `Cache-Control: no-store`.
- The response aggregates existing application profile, education, employment, work authorization, projects,
  career preferences, confirmed user skills, version-scoped resume evidence, and project technologies. It does
  not persist a CandidateProfile table or duplicate source facts.
- Reconciled catalog skills use exact catalog IDs and retain every source separately: `CONFIRMED_BY_USER`,
  `RESUME_EVIDENCE`, or `PROJECT`. Custom text is grouped only by its stored normalized value. Neither parsing
  nor this GET creates, confirms, deletes, or upgrades a `UserSkill`.
- Resume evidence returns its resume/version/item provenance and recognized catalog links, but never raw extracted
  text, storage keys, file hashes, download URLs, or file bytes.

### 2.6 Job Foundation and Discovery (Phases 9–11)

- `GET /api/v1/jobs`: returns one deterministic page of active shared jobs. It accepts bounded literal
  case-insensitive `keyword` (or `query`) across title, company, and description; `location` over normalized
  location text; `company`; `requirement` over canonical skill names and requirement descriptions;
  `employment_type` (or `type`); `work_mode`; `page` (1–10,000); `page_size` (1–50); and fixed `sort`
  (`newest`, `oldest`, `title_asc`, `title_desc`). The response is
  `{items, page, page_size, total, total_pages}`. The default sort is posted timestamp descending with
  nulls last, discovery timestamp descending, and ID ascending. Other fixed sorts retain ID as a tie-breaker.
  The endpoint requires a current session, creates no rows, requires no CSRF header, and returns
  `Cache-Control: no-store`.
- `GET /api/v1/jobs/{id}`: returns one active shared job with normalized locations and explicit skill,
  education, and eligibility requirements. Inactive and unknown IDs return the same `JOB_NOT_FOUND` 404.
- Jobs have no user ownership relation. The list rejects unknown, duplicate, and client ownership query
  parameters; details reject all query parameters. Neither endpoint loads
  Candidate Profile, skills, resumes, education, employment, work authorization, applications, evaluations, or
  matching data.
- Responses contain only normalized job fields. They never return raw ingestion snapshots, payload or current hashes,
  source adapters, external source IDs, or requirement `source_evidence`. Description and requirement strings
  are untrusted plain text for the UI to render safely.
- Phase 10 adds internal ingestion only: `SourceAdapterRegistry`/`SourceAdapter` feeds a strict DTO through the
  normalizer, service, and repository into existing source records, snapshots, normalized jobs, and replacement
  requirement rows. It adds no OpenAPI operation or public source-provenance field.
- There is no public job creation, import, recommendation, candidate-fit, resume-alignment, application, or
  mutation endpoint. Phase 11 discovery is catalog search only; it never uses candidate facts, preferences,
  resume evidence, or scoring.

### 2.7 Resume Evaluation (deferred)
- `POST /api/v1/resume-evaluations` (Types: `GENERAL_QUALITY`, `ROLE_ALIGNMENT`, `JOB_ALIGNMENT`)
- `GET /api/v1/resume-evaluations` (`?resume_version_id=...&page=...`)
- `GET /api/v1/resume-evaluations/{id}`, `DELETE /api/v1/resume-evaluations/{id}`
- `POST /api/v1/resume-versions/{id}/bullet-analysis` (Interactive bullet critique)

### 2.8 Application Tracker (deferred)
- `GET /api/v1/applications` (Filter by status, company; powers list and Kanban UI)
- `POST /api/v1/applications` (Creates tracked application in `SAVED` status)
- `GET /api/v1/applications/{id}`
- `PATCH /api/v1/applications/{id}` (Metadata updates using `expected_version`)
- `POST /api/v1/applications/{id}/transitions` (State transition with `expected_version`; atomic status history insert)
- `GET /api/v1/applications/{id}/history` (Audit log of status changes)
- `GET /api/v1/applications/{id}/preparation` (Assembles facts, answers, resume for manual submission)
- `DELETE /api/v1/applications/{id}`
