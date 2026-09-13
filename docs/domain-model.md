# StudentSuccessful — Domain Model Specification (Phase 1 Approved Baseline)

**Document Version:** 1.1 (Approved Baseline)  
**Phase:** SDLC Phase 1 — Domain Model  
**Status:** Approved by Mentee & Mentor  
**Date:** September 5, 2026  

---

## 1. Domain Bounded Contexts Overview

The StudentSuccessful platform is architected as a clean modular monolith across six bounded contexts:

```text
                                     MODULAR MONOLITH
┌───────────────────────────────────────────┬───────────────────────────────────────────┐
│ 1. Identity & Application Factual Context │ 2. Taxonomy & Job Corpus Context          │
│    - User                                 │    - Canonical Taxonomies (Role, Skill)   │
│    - ApplicationProfile (Contact/Identity)│    - JobSourceRecord & RawJobSnapshot     │
│    - EducationRecord (1:N)                │    - NormalizedJob & JobLocation (1:N)    │
│    - EmploymentRecord (1:N)               │    - Structured Requirements (Skill/Edu/  │
│    - WorkAuthorization (1:N per country)  │      Eligibility)                         │
│    - ApplicationAnswer (Unique per key)   │                                           │
├───────────────────────────────────────────┼───────────────────────────────────────────┤
│ 3. Preference & Search Context            │ 4. Resume & Evidence Provenance Context   │
│    - CareerPreferences (1:1 Aggregate)    │    - Resume (Family) & ResumeVersion (1:N)│
│    - UserPreferredRole / Industry /       │    - ResumeEvidenceItem (1:N)             │
│      Location / Company / Skill (Join)    │    - ResumeEvidenceSkill (Join with Skill)│
├───────────────────────────────────────────┼───────────────────────────────────────────┤
│ 5. Candidate Knowledge Context            │ 6. Matching, Evaluation & Tracking Context│
│    - CandidateProfile (Domain Aggregate)  │    - MatchingService (On-Demand DTO)      │
│    - CandidateSkill (Persisted States     │    - ResumeEvaluation (Versioned Snapshot)│
│      A, B, C; State D derived)            │    - Application (Linked to ResumeVersion)│
│    - CandidateSkillEvidence (Join)        │    - ApplicationStatusHistory (Audit Log) │
└───────────────────────────────────────────┴───────────────────────────────────────────┘
```

---

## 2. Entity Specifications

### 2.1 Identity & Factual Application Context

#### Entity: `User`
- **Responsibility:** Authenticated root identity anchor.
- **Fields:**
  - `id`: UUID (PK)
  - `email`: String (Unique, Indexed, Lowercase)
  - `password_hash`: String (Argon2id)
  - `is_active`: Boolean
  - `created_at`, `updated_at`: Timestamp UTC
- **Relationships:**
  - `1:1` with `ApplicationProfile`
  - `1:1` with `CareerPreferences`
  - `1:N` with `EducationRecord`, `EmploymentRecord`, `WorkAuthorization`
  - `1:N` with `ApplicationAnswer`
  - `1:N` with `Resume`
  - `1:N` with `CandidateSkill`
  - `1:N` with `Application`

#### Entity: `ApplicationProfile`
- **Responsibility:** Strictly factual contact and legal identity information. (Education, employment, and work authorization extracted into 1:N relations).
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`, Unique)
  - `legal_first_name`, `legal_middle_name`, `legal_last_name`, `preferred_name`: String
  - `phone_number`: Optional String (trimmed international format, 5–20 digits with dialing punctuation and optional extension; no inferred country code)
  - `address_street`, `address_city`, `address_state_province`, `address_postal_code`, `address_country_code`: String
  - `linkedin_url`, `github_url`, `portfolio_url`: Optional Validated URLs
  - `created_at`, `updated_at`: Timestamp UTC

#### Entity: `EducationRecord` (1:N per User)
- **Responsibility:** Represents individual academic milestones (College, University, Bachelor's, Master's, Exchange).
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `institution_name`: String
  - `degree_level`: Enum (`BS`, `BA`, `MS`, `PHD`, `ASSOCIATES`, `OTHER`)
  - `major`: String
  - `minor`: Optional String
  - `study_year`: Enum (`YEAR_1`, `YEAR_2`, `YEAR_3`, `YEAR_4`, `YEAR_5_PLUS`, `GRADUATE`, `OTHER`)
  - `start_date`: Date
  - `expected_grad_month`: Integer (1–12), `expected_grad_year`: Integer (2000–2100)
  - `gpa_value`: Optional Decimal NUMERIC(5,2), `gpa_scale`: Optional Decimal NUMERIC(5,2) (native pair, e.g., 3.54 / 4.00, 4.20 / 4.33 or 100.00 / 100.00; never converted)
  - `gpa_include_on_apps`: Boolean (default false; enabling requires a complete GPA pair)
  - `is_primary`: Boolean (default false; at most one explicitly selected primary per user)
  - `created_at`, `updated_at`: Timestamp UTC

- **Phase 6C invariants:** GPA is either absent as a pair or finite with 0 ≤ value ≤ positive scale, at most two fractional digits. Graduation month/year cannot precede the start month/year; the same month is valid. Primary selection demotes the previous primary atomically; deleting a primary does not select a replacement. Education requires the User only, not an ApplicationProfile row. Facts are never inferred from resume, email, links or other fields.

#### Entity: `EmploymentRecord` (1:N per User)
- **Responsibility:** Factual work history items for application completion.
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `employer_name`: String
  - `job_title`: String
  - `location`: String
  - `start_date`: Date
  - `end_date`: Optional Date
  - `currently_employed`: Boolean
  - `description`: Optional Text
  - `created_at`, `updated_at`: Timestamp UTC

- **Phase 6D behavior:** User-entered Application Facts; no inference from profile, education, resume or external links. Free-text location is historical employment location, not Career Preferences or a taxonomy link. Description is factual text, preserved without skill extraction.
- **Dates:** currently_employed defaults false and then requires end_date. When true, end_date may be absent or present (such as a known contract end). Changing current status does not clear it. Present end_date must be >= start_date. Final merged PATCH state is validated under an owner-scoped EmploymentRecord row lock.

#### Entity: `WorkAuthorization` (1:N per User & Country)
- **Responsibility:** Precise, multi-country legal eligibility modeling. Prevents global status conflation.
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `country_code`: String (two uppercase ASCII letters, e.g. "US", "CA"; format only, not ISO membership)
  - `authorization_status`: Enum (`CITIZEN`, `PERMANENT_RESIDENT`, `STUDENT_WORK_AUTHORIZATION`, `TEMPORARY_WORK_AUTHORIZATION`, `OTHER`, `STUDENT_VISA_CPT_OPT`, `WORK_VISA`)
  - `requires_current_sponsorship`: Boolean
  - `requires_future_sponsorship`: Boolean
  - `notes`: Optional String
  - `last_confirmed_at`: Timestamp UTC
  - `created_at`, `updated_at`: Timestamp UTC
- **Constraints:**
  - Unique constraint on `(user_id, country_code)`.

#### Entity: `ApplicationAnswer`
- **Responsibility:** Normalized reusable question-and-answer store.
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `normalized_question_key`: String (e.g., `sponsorship_required`, `relocation_willingness`)
  - `original_question_prompt`: Text
  - `answer_value`: Text
  - `answer_type`: Enum (`BOOLEAN`, `TEXT`, `CHOICE`, `NUMERIC`)
  - `is_sensitive`: Boolean (Demographic, disability, clearance)
  - `user_approved_for_reuse`: Boolean (False by default for sensitive)
  - `last_confirmed_at`: Timestamp UTC
  - `created_at`, `updated_at`: Timestamp UTC
- **Constraints:**
  - Unique constraint on `(user_id, normalized_question_key)`.

---

### 2.2 Preference & Search Context

#### Entity: `CareerPreference` (Aggregate Root)
- **Responsibility:** Search filters decoupled from identity.
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`, Unique)
  - `work_modes`: Array of Enums (`ON_SITE`, `HYBRID`, `REMOTE`)
  - `employment_types`: Array of Enums (`INTERNSHIP`, `CO_OP`, `NEW_GRAD`, `PART_TIME`)
  - `created_at`, `updated_at`: Timestamp UTC

#### Relational Join Entities (Replacing Foreign Key Arrays):
- `UserPreferredRole`: `(user_id, role_id)`.
- `UserPreferredIndustry`: `(user_id, industry_id)`.
- `UserPreferredLocation`: `(user_id, location_id)`.
- `UserPreferredCompany`: `(user_id, company_id)`.
- `UserPreferredSkill`: `(user_id, skill_id)`; technology interest only.
- `CareerPreferenceCustomValue`: `(career_preference_id, preference_type, value, normalized_value)`; separate custom entries, unique by root/type/normalized value.

---

### 2.3 Resume & Evidence Context

#### Entity: `Resume` (Document Family)
- **Responsibility:** Logical document grouping (e.g., "Backend Resume", "Systems Resume").
- **Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `title`: String
  - `created_at`: Timestamp UTC

#### Entity: `ResumeVersion` (Immutable Document Instance)
- **Responsibility:** The physical file instance submitted or parsed.
- **Fields:**
  - `id`: UUID (PK)
  - `resume_id`: UUID (FK $\rightarrow$ `Resume.id`)
  - `version_number`: Integer
  - `storage_key`: String (server-managed opaque key)
  - `file_format`: Enum (`PDF`, `DOCX`)
  - `file_size_bytes`: Integer
  - `file_hash_sha256`: String
  - `is_primary_active`: Boolean
  - `parse_status`: Enum (`PENDING`, `PARSED_SUCCESS`, `PARSE_FAILED`, `USER_MODIFIED`)
  - `raw_extracted_text`: Text (derived, normalized, maximum 262,144 characters)
  - `created_at`: Timestamp UTC

  The uploaded-file identity fields remain immutable after upload. Parsing is an
  explicit operation that may update only `parse_status`, `raw_extracted_text`,
  and evidence owned by this exact version.

#### Entity: `ResumeEvidenceItem`
- **Responsibility:** Verbatim parsed section bullet.
- **Fields:**
  - `id`: UUID (PK)
  - `resume_version_id`: UUID (FK $\rightarrow$ `ResumeVersion.id`)
  - `ordinal`: Integer (zero-based source order; unique within one version)
  - `category`: Enum (`EDUCATION`, `EXPERIENCE`, `PROJECTS`, `SKILLS`, `OTHER`)
  - `section_header`: String
  - `bullet_text`: Text
  - `created_at`: Timestamp UTC

  Items are parser-derived provenance, replaced atomically when that same
  `ResumeVersion` is successfully reparsed. They are not user-authored facts.

#### Entity: `ResumeEvidenceSkill` (Join Entity)
- **Responsibility:** Relational link between parsed evidence and canonical skill.
- **Fields:**
  - `evidence_item_id`: UUID (FK $\rightarrow$ `ResumeEvidenceItem.id`)
  - `skill_id`: UUID (FK $\rightarrow$ `Skill.id`)
  - `parser_confidence`: Decimal (0.00 – 1.00)

  The composite key is (`evidence_item_id`, `skill_id`). Links are conservative
  exact catalog-name or explicit-alias matches and never create or alter a
  `UserSkill`, Career Preference, Project, Employment, or Education fact.

---

### 2.4 Candidate Knowledge Context

#### Domain Aggregate: `CandidateProfile`
- **Responsibility:** Read-only, in-memory projection returned by `CandidateProfileService`; it is not a
  database table or editable aggregate.
- **Inputs:** Optional `ApplicationProfile`; owned `EducationRecord`, `EmploymentRecord`, and
  `WorkAuthorization` rows; `CareerPreference`; `Project` technologies; confirmed `UserSkill` and
  `UserCustomSkill`; and version-scoped `ResumeEvidenceItem` / `ResumeEvidenceSkill` rows.
- **Catalog reconciliation:** A `Skill.id` is the only catalog identity key. A response skill may retain one
  explicit-user confirmation, any number of independent resume-evidence citations, and project-usage sources.
  Exact normalized custom text may be grouped only with its existing user/project custom sources.
- **Provenance rule:** `UserSkill` is an explicit confirmation, `ResumeEvidenceSkill` is detected document
  evidence, and `ProjectSkill` is project usage. They remain separate response sources; no source changes
  confidence, creates a fact, or infers proficiency, seniority, or capability.
- **Persistence rule:** There is no `CandidateSkill`, `CandidateSkillEvidence`, or `CandidateProfile` table.
  The projection never writes its inputs and never exposes raw extracted text or managed resume file metadata.

---

### 2.5 Job Corpus Context

#### Entity: `JobSourceRecord`
- **Responsibility:** Reusable internal identity for one source-adapter/external-ID pair.
- **Fields:**
  - `id`: UUID (PK)
  - `source_adapter`: String identifying the internal source adapter
  - `external_id`: String
  - `source_url`: String
  - `created_at`: Timestamp UTC
- **Constraints:**
  - Unique on `(source_adapter, external_id)`.
  - Adapter and external ID are nonblank and contain no control characters; `source_url` is an HTTP(S) URL with no whitespace.

#### Entity: `RawJobSnapshot` (1:N per JobSourceRecord)
- **Responsibility:** Immutable, deduplicated snapshots of canonical whitelisted normalized source facts.
- **Fields:**
  - `id`: UUID (PK)
  - `job_source_record_id`: UUID (FK $\rightarrow$ `JobSourceRecord.id`)
  - `raw_payload`: JSONB
  - `payload_hash_sha256`: String
  - `fetched_at`: Timestamp UTC
- **Constraints:** `payload_hash_sha256` is lowercase 64-hex SHA-256 and is unique with its source record.

#### Entity: `NormalizedJob`
- **Responsibility:** Standardized shared job opportunity. Phase 10 creates or updates it internally from its
  existing source record and canonical snapshot; Phase 9 exposes only a read-only normalized view.
- **Fields:**
  - `id`: UUID (PK)
  - `job_source_record_id`: UUID (FK $\rightarrow$ `JobSourceRecord.id`, Unique)
  - `company_id`: UUID (FK $\rightarrow$ `Company.id`)
  - `title`: String
  - `description`: Optional plain-text normalized description
  - `role_id`: UUID (FK $\rightarrow$ `Role.id`)
  - `employment_type`: Enum (`INTERNSHIP`, `CO_OP`, `NEW_GRAD`, `PART_TIME`)
  - `career_level`: External-job fact, including `UNSPECIFIED`
  - `work_mode`: Enum (`ON_SITE`, `HYBRID`, `REMOTE`)
  - `application_url`: HTTP(S) URL with no whitespace
  - `current_payload_hash_sha256`: Optional private hash of the canonical snapshot currently applied to this job
  - `is_active`: Boolean
  - `posted_at`: Optional Timestamp UTC
  - `discovered_at`: Timestamp UTC set on first ingestion
  - `last_verified_at`: Timestamp UTC advanced on every successful source fetch, including an unchanged
    deduplicated snapshot

#### Entity: `JobLocation` (1:N per NormalizedJob)
- **Responsibility:** Multiple office locations per job.
- **Fields:**
  - `id`: UUID (PK)
  - `job_id`: UUID (FK $\rightarrow$ `NormalizedJob.id`)
  - `location_id`: Optional UUID (FK $\rightarrow$ `Location.id`)
  - `location_raw`: String (e.g. "Toronto, ON or Vancouver, BC")

#### Structured Job Requirements:
- `JobSkillRequirement`: `(job_id, skill_id, importance: source-provided String, description)`. The current model and database do not constrain this vocabulary; Phase 9 fixtures use `REQUIRED` and `PREFERRED`.
- `JobEducationRequirement`: `(job_id, degree_level, target_grad_start, target_grad_end)`
- `JobEligibilityRequirement`: `(job_id, requirement_type: source-provided String, value, description, source_evidence)`. The current model and database do not constrain this vocabulary; Phase 9 fixtures use `WORK_AUTHORIZATION`.

Phase 10's internal adapter → strict DTO → normalizer → service → repository pipeline reuses source records and
snapshots, then replaces normalized requirement rows as part of the job update. Phase 9 exposes active jobs and
these normalized requirement facts to authenticated users only. It never exposes `RawJobSnapshot`, job-source
identifiers, snapshot hashes, or `source_evidence`, and does not join this context with any candidate record or
make a comparison.

---

### 2.6 Evaluation, Matching & Tracking Context (deferred)

The baseline schema contains future-facing entities in this context, but Phase 9 adds no router, service,
workflow, UI, write path, score, or evaluation behavior for them.

#### DTO (On-Demand): `JobMatchResult`
- **Responsibility:** Computed dynamically in memory by `MatchingService`; not persisted on every page browse.
- **Components:**
  - `eligibility_status`: Enum (`COMPATIBLE`, `INCOMPATIBLE`, `UNKNOWN`)
  - `eligibility_reasons`: Array of Strings
  - `scoring_profile_used`: String
  - `total_fit_score`: Integer (0–100)
  - `fit_tier`: Enum (`STRONG_FIT`, `MODERATE_FIT`, `GROWTH_OPPORTUNITY`, `INELIGIBLE`)
  - `component_breakdown`: Key-Value score map
  - `matched_skills`: Structured list with `skill_id`, `name`, and evidence citations
  - `partial_skills`: Claimed in profile without resume evidence
  - `missing_skills`: Unmatched job requirements

#### Entity: `ResumeEvaluation` (Persisted Snapshot)
- **Responsibility:** Stores user-requested rubric alignment snapshots.
- **Fields:**
  - `id`: UUID (PK)
  - `resume_version_id`: UUID (FK $\rightarrow$ `ResumeVersion.id`)
  - `evaluation_type`: Enum (`GENERAL_QUALITY`, `ROLE_ALIGNMENT`, `JOB_ALIGNMENT`, `BULLET_ANALYSIS`)
  - `target_role_id`: Optional UUID (FK $\rightarrow$ `Role.id`)
  - `target_job_id`: Optional UUID (FK $\rightarrow$ `NormalizedJob.id`)
  - `rubric_version`: String
  - `overall_score`: Integer (0–100 alignment score)
  - `category_scores`: JSONB
  - `itemized_reasons`: Array of Strings
  - `suggested_improvements`: Array of Strings
  - `bullet_analysis_detail`: Optional JSONB
  - `evaluated_at`: Timestamp UTC

#### Entity: `Application` & `ApplicationStatusHistory`
- **Responsibility:** State machine tracking external job applications.
- **`Application` Fields:**
  - `id`: UUID (PK)
  - `user_id`: UUID (FK $\rightarrow$ `User.id`)
  - `job_id`: UUID (FK $\rightarrow$ `NormalizedJob.id`)
  - `resume_version_id`: UUID (FK $\rightarrow$ `ResumeVersion.id`, Immutable historic pointer)
  - `current_status`: Enum (`SAVED`, `PREPARING`, `APPLIED`, `ONLINE_ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `WITHDRAWN`)
  - `applied_at`: Optional Timestamp UTC
  - `deadline_at`, `next_follow_up_at`: Optional Timestamp UTC
  - `notes`: Text
  - `created_at`, `updated_at`: Timestamp UTC
- **`ApplicationStatusHistory` Fields:**
  - `id`: UUID (PK)
  - `application_id`: UUID (FK $\rightarrow$ `Application.id`)
  - `previous_status`: Optional Enum
  - `new_status`: Enum
  - `rejection_stage`: Optional Enum (`AFTER_APPLICATION`, `AFTER_OA`, `AFTER_INTERVIEW`, `POSITION_CLOSED`, `UNKNOWN`, `OTHER`)
  - `notes`: Optional Text
  - `transitioned_at`: Timestamp UTC

---

## 3. Non-Linear Application Workflow Policy

Transitions between application statuses are non-linear:

```text
[SAVED] ──► [PREPARING] ──► [APPLIED]
   │             │              │
   │             │              ├──► [ONLINE_ASSESSMENT] ──► [INTERVIEW] ──► [OFFER]
   │             │              │            │                    │
   │             │              │            ├──► [REJECTED]      ├──► [REJECTED]
   │             │              │            │                    │
   │             │              ├──► [INTERVIEW]                  └──► [INTERVIEW (Round N)]
   │             │              │
   │             │              └──► [REJECTED]
   │             │
   └─────────────┴────────────────────────────────────────────────► [WITHDRAWN]
```


## Phase 6E implemented Work Authorization semantics

Work Authorization is one-to-many per User, with exactly one record per user/country and no ApplicationProfile prerequisite. Country identifies the authorization jurisdiction, not residence, nationality or desired job location. API normalization trims and uppercases exactly two ASCII letters; neither API nor database claims ISO membership validation.

The structured statuses are CITIZEN, PERMANENT_RESIDENT, STUDENT_WORK_AUTHORIZATION, TEMPORARY_WORK_AUTHORIZATION, OTHER, STUDENT_VISA_CPT_OPT and WORK_VISA. Phase 6E adds the two generic authorization choices while retaining every baseline value unchanged. CPT/OPT is explicitly a US-specific legacy label; WORK_VISA is a retained legacy label. These are user-selected categories, not determinations of legal eligibility. No legacy facts are mapped or reinterpreted, and no legal equivalence is asserted.

Current and future sponsorship are independent explicit booleans. Status never sets sponsorship, and sponsorship never sets status. Notes are optional factual text, trimmed, limited to 255 characters; blank/null clears. Do not enter government document numbers. Nothing is inferred from notes, location, profile, education, employment or external sources. No job compatibility is computed.

last_confirmed_at is server-managed UTC: set on POST and refreshed on successful PATCH containing at least one editable fact, even if its value is unchanged. GET and empty PATCH preserve the timestamp. The UI sends only changed facts, so an unchanged form closes without reconfirming. Clients cannot supply IDs, ownership or timestamps.


## Phase 6F implemented preference behavior

Career Preferences are explicit desired choices, separate from Profile, Education, Employment, Work Authorization and resume evidence. Technology interests use Skill/UserPreferredSkill only and do not create UserSkill or capability claims. No preferences are inferred.

GET `/api/v1/preferences` is authenticated, returns a deterministic complete selection object (empty arrays when unsaved), and creates no row. PUT on the same route is authenticated, requires the current session CSRF token, and replaces the full aggregate: role_ids, industry_ids, location_ids, company_ids, skill_ids, work_modes, employment_types and custom_values. Omitted arrays mean empty and remove previous selections. Success responses use no-store; body/query user_id is rejected. IDs are UUIDs; duplicate canonical IDs and structured choices are deduplicated and sorted. Unknown IDs return controlled 422 before any replacement.

Work modes: ON_SITE, HYBRID, REMOTE. Employment types: INTERNSHIP, CO_OP, NEW_GRAD, PART_TIME. Custom entries have preference_type ROLE/INDUSTRY/LOCATION/COMPANY/SKILL and display value (nonblank, maximum 150 characters). Display text is preserved exactly. Normalized uniqueness uses whitespace collapse/trim plus Unicode casefold, with a maximum normalized length of 150. Duplicate normalized values within a type are rejected; matching values in different types are allowed. Custom entries never become canonical taxonomy entries, even when their labels match.

The service locks the existing User row for aggregate replacement, validates all canonical IDs (with key-share locks against concurrent deletion), then updates the root, joins and custom values in one transaction and commits once. Identical PUT preserves existing root/custom row IDs and timestamps. GET takes a shared User-row lock for a coherent multi-table read. Repository methods never commit. Different users are independent.

Catalog endpoints are authenticated read-only GETs and require no CSRF. Roles support q and active (default true; false returns inactive roles). Skills support q/category and return active skills. Companies support q. Locations support country_code (case-insensitive two-letter filter) and q over city/state-province. Industries have no filters. Search is literal case-insensitive substring, not wildcard input. Names sort case-insensitively then by ID; locations sort country, case-insensitive city, state/province, ID. No catalog mutations are exposed. Existing inactive canonical IDs remain valid preferences; selected items missing from active catalogs stay visible as removable saved IDs in the form.

The `/preferences` form loads catalogs from these APIs, supports multiple selections and explicit Other entries, and saves one complete PUT. New installations have no seeded canonical catalog: empty catalog messaging and custom values are supported. Browser verification fixtures are disposable and are never seeded by migrations. Phase 6G and matching remain deferred.
