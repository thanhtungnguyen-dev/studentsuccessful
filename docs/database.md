# StudentSuccessful — Database Design Specification (Phase 3.1 Approved Baseline)

**Document Version:** 1.2 (Phase 3.1 Migration Delta Incorporated)  
**Phase:** SDLC Phase 3.1 — Database Delta & Schema Baseline  
**Status:** Approved by Mentee & Mentor  
**Date:** September 5, 2026  

---

## 1. Schema Invariants & Database Integrity Rules

StudentSuccessful uses PostgreSQL as its primary relational store. The schema design enforces:
1. **Third Normal Form (3NF) for Core Relations:** Eliminates update and insertion anomalies across users, educations, work authorizations, jobs, skills, and applications.
2. **Explicit Join Entities (No FK UUID Arrays):** Relationships like `user_preferred_roles`, `job_locations`, `job_industries`, `resume_evidence_skills`, and `user_skills` are governed by relational tables with composite keys and database-level foreign key constraints.
3. **Server-Managed Session Security (`user_sessions`):**
   - The browser receives a high-entropy random cookie token (`__Host-ss_session`).
   - The database persists only `session_token_hash` (SHA-256) and `csrf_token_hash` (SHA-256). Raw credentials are never stored.
4. **Data Deletion Rights vs. Application History:**
   - Deleting a resume version sets `applications.resume_version_id = NULL` (`ON DELETE SET NULL`), while immutable historical metadata snapshots (`resume_title_snapshot`, `resume_hash_snapshot`) are retained on the application row.
   - Complete user account deletion cascades cleanly across all user-owned data.
5. **Single Active Primary Resume per Logical Family:**
   - Enforced by a partial unique index: `CREATE UNIQUE INDEX idx_user_primary_resume_version ON resume_versions(resume_id) WHERE is_primary_active = TRUE;`
6. **Generic Support for "Other" via Custom Preference Entities:**
   - `career_preference_custom_values` allows custom entries for roles, industries, locations, companies, and skills without polluting canonical taxonomy tables.
7. **Explicit Job-Industry Association (`job_industries`):**
   - Direct many-to-many join connecting jobs to industries for structured filtering.
8. **Separation of Employment Type from Career Level:**
   - `employment_type`: `INTERNSHIP`, `CO_OP`, `FULL_TIME`, `PART_TIME`, `CONTRACT`.
   - `career_level`: `STUDENT`, `INTERN`, `NEW_GRAD`, `ENTRY_LEVEL`, `EXPERIENCED`, `UNSPECIFIED`.
9. **Explicit `UNSPECIFIED` Support for External Facts:**
   - External job attributes (`work_mode`, `career_level`) support `UNSPECIFIED` by default.
10. **Typed Job Eligibility Requirements:**
    - Machine-readable enum criteria (`WORK_AUTH_COUNTRY`, `SPONSORSHIP_CURRENT`, `SPONSORSHIP_FUTURE`, `SECURITY_CLEARANCE`, `ENROLLMENT_COUNTRY`, `GRADUATION_WINDOW`) with structured string/date target values.
11. **Current vs. Future Sponsorship Modeling:**
    - Distinguishes `requires_current_sponsorship` and `requires_future_sponsorship` on both candidate authorization and employer requirements.
12. **Timezone-Aware UTC Instants:**
    - All event timestamps use `TIMESTAMPTZ` (UTC). Calendar dates use `DATE`.
13. **Case-Insensitive Email Integrity:**
    - Guaranteed at database level via `CREATE UNIQUE INDEX idx_users_email_lower ON users (lower(email));`.
14. **Optimistic Locking with Co-Located Audit Entries:**
    - `applications.version` increments on status updates (`UPDATE ... WHERE id = :id AND version = :expected`).
    - The status update and `application_status_histories` insert occur strictly inside the **same database transaction**.
15. **Fixture Separation:**
    - Schema migrations (`backend/alembic/versions/`) contain DDL only.
    - Development job fixtures reside in `tests/fixtures/` and are loaded via `scripts/seed_dev.py`, never in production migrations.
16. **Internal Job-Ingestion Integrity:**
    - Source identity is unique on adapter/external ID; canonical whitelisted normalized snapshots are deduplicated per source record by their SHA-256 hash.
    - Revision `c6f2a8d4b9e1` rejects blank/control-character source adapter and external-ID values, non-HTTP(S) or whitespace-containing source and application URLs, and snapshot hashes other than lowercase 64-hex SHA-256.

---

## 2. Complete Relational Schema DDL (Including Phase 3.1 Deltas)

### 2.1 Identity, Sessions & Factual Application Tables

```sql
-- 1. users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX idx_users_email_lower ON users (lower(email));

-- 2. user_sessions (Phase 3.1 Delta: Server-Managed Cookie Session Persistence)
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token_hash CHAR(64) NOT NULL UNIQUE, -- SHA-256 of browser token
    csrf_token_hash CHAR(64) NOT NULL,           -- SHA-256 of CSRF token
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);
CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);

-- 3. application_profiles
CREATE TABLE application_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    legal_first_name VARCHAR(100) NOT NULL,
    legal_middle_name VARCHAR(100),
    legal_last_name VARCHAR(100) NOT NULL,
    preferred_name VARCHAR(100),
    phone_number VARCHAR(30),
    address_street VARCHAR(255),
    address_city VARCHAR(100),
    address_state_province VARCHAR(100),
    address_postal_code VARCHAR(30),
    address_country_code CHAR(2),
    linkedin_url VARCHAR(500),
    github_url VARCHAR(500),
    portfolio_url VARCHAR(500),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 4. education_records
CREATE TABLE education_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    institution_name VARCHAR(255) NOT NULL,
    degree_level VARCHAR(50) NOT NULL, -- 'BS', 'BA', 'MS', 'PHD', 'ASSOCIATES', 'OTHER'
    major VARCHAR(150) NOT NULL,
    minor VARCHAR(150),
    study_year VARCHAR(50) NOT NULL, -- 'YEAR_1', 'YEAR_2', 'YEAR_3', 'YEAR_4', 'YEAR_5_PLUS', 'GRADUATE', 'OTHER'
    start_date DATE NOT NULL,
    expected_grad_month SMALLINT NOT NULL CHECK (expected_grad_month BETWEEN 1 AND 12),
    expected_grad_year SMALLINT NOT NULL CHECK (expected_grad_year BETWEEN 2000 AND 2100),
    gpa_value NUMERIC(5, 2),
    gpa_scale NUMERIC(5, 2),
    gpa_include_on_apps BOOLEAN NOT NULL DEFAULT FALSE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_education_gpa_pair CHECK ((gpa_value IS NULL) = (gpa_scale IS NULL)),
    CONSTRAINT ck_education_gpa_nonnegative CHECK (gpa_value >= 0 AND gpa_value <> 'NaN'::numeric),
    CONSTRAINT ck_education_gpa_scale_positive CHECK (gpa_scale > 0 AND gpa_scale <> 'NaN'::numeric),
    CONSTRAINT ck_education_gpa_within_scale CHECK (gpa_value <= gpa_scale),
    CONSTRAINT ck_education_gpa_disclosure CHECK (NOT gpa_include_on_apps OR (gpa_value IS NOT NULL AND gpa_scale IS NOT NULL)),
    CONSTRAINT ck_education_date_order CHECK ((EXTRACT(YEAR FROM start_date), EXTRACT(MONTH FROM start_date)) <= (expected_grad_year, expected_grad_month))
);
CREATE INDEX idx_education_records_user_id ON education_records(user_id);

CREATE UNIQUE INDEX uq_education_primary_user ON education_records(user_id) WHERE is_primary = TRUE;

-- 5. employment_records
CREATE TABLE employment_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    employer_name VARCHAR(255) NOT NULL,
    job_title VARCHAR(150) NOT NULL,
    location VARCHAR(150),
    start_date DATE NOT NULL,
    end_date DATE,
    currently_employed BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_employment_end_date CHECK (currently_employed = TRUE OR end_date IS NOT NULL),
    CONSTRAINT ck_employment_date_order CHECK (end_date IS NULL OR end_date >= start_date)
);
CREATE INDEX idx_employment_records_user_id ON employment_records(user_id);

-- 6. work_authorizations
CREATE TABLE work_authorizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    country_code CHAR(2) NOT NULL,
    authorization_status VARCHAR(50) NOT NULL,
    requires_current_sponsorship BOOLEAN NOT NULL DEFAULT FALSE,
    requires_future_sponsorship BOOLEAN NOT NULL DEFAULT FALSE,
    notes VARCHAR(255),
    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_work_auth_user_country UNIQUE (user_id, country_code),
    CONSTRAINT ck_work_authorization_country_code CHECK (country_code ~ '^[A-Z]{2}$'),
    CONSTRAINT ck_work_authorization_status CHECK (authorization_status IN ('CITIZEN', 'PERMANENT_RESIDENT', 'STUDENT_WORK_AUTHORIZATION', 'TEMPORARY_WORK_AUTHORIZATION', 'OTHER', 'STUDENT_VISA_CPT_OPT', 'WORK_VISA'))
);

-- 7. application_answers
CREATE TABLE application_answers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    normalized_question_key VARCHAR(100) NOT NULL,
    original_question_prompt TEXT NOT NULL,
    answer_value TEXT NOT NULL,
    answer_type VARCHAR(30) NOT NULL, -- 'BOOLEAN', 'TEXT', 'CHOICE', 'NUMERIC'
    is_sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    user_approved_for_reuse BOOLEAN NOT NULL DEFAULT FALSE,
    last_confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, normalized_question_key)
);
```

---

### 2.2 Taxonomy Tables

```sql
-- 8. roles
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 9. skills
CREATE TABLE skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL, -- 'LANGUAGE', 'FRAMEWORK', 'DATABASE', 'TOOL', 'CLOUD', 'SYSTEMS_CONCEPT', 'AI_ML'
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 10. skill_aliases
CREATE TABLE skill_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    alias VARCHAR(100) NOT NULL,
    normalized_alias VARCHAR(100) NOT NULL,
    UNIQUE (skill_id, normalized_alias)
);
CREATE INDEX idx_skill_aliases_lookup ON skill_aliases(normalized_alias);

-- 11. companies
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    domain VARCHAR(150),
    is_verified BOOLEAN NOT NULL DEFAULT TRUE
);

-- 12. locations
CREATE TABLE locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    country_code CHAR(2) NOT NULL,
    state_province VARCHAR(100),
    city VARCHAR(100) NOT NULL
);

-- 13. industries
CREATE TABLE industries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE
);
```

---

### 2.3 Career Preferences & Generic "Other" Values

```sql
-- 14. career_preferences
CREATE TABLE career_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    work_modes TEXT[] NOT NULL,
    employment_types TEXT[] NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 15. career_preference_custom_values (Phase 3.1 Delta: Generic "Other" Storage)
CREATE TABLE career_preference_custom_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    career_preference_id UUID NOT NULL REFERENCES career_preferences(id) ON DELETE CASCADE,
    preference_type VARCHAR(30) NOT NULL, -- 'ROLE', 'INDUSTRY', 'LOCATION', 'COMPANY', 'SKILL'
    value VARCHAR(150) NOT NULL,
    normalized_value VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (career_preference_id, preference_type, normalized_value)
);

-- 16. user_preferred_roles (Canonical Joins)
CREATE TABLE user_preferred_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- 17. user_preferred_industries
CREATE TABLE user_preferred_industries (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    industry_id UUID NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, industry_id)
);

-- 18. user_preferred_locations
CREATE TABLE user_preferred_locations (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    location_id UUID NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, location_id)
);

-- 19. user_preferred_companies
CREATE TABLE user_preferred_companies (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, company_id)
);

-- 20. user_preferred_skills
CREATE TABLE user_preferred_skills (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, skill_id)
);
```

---

### 2.4 Resumes, Evidence & Confirmed Skills

```sql
-- 21. resumes (Logical Document Family)
CREATE TABLE resumes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_resumes_user_id ON resumes(user_id);

-- 22. resume_versions (Physical Upload Instance)
CREATE TABLE resume_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_id UUID NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
    version_number INT NOT NULL DEFAULT 1,
    storage_key VARCHAR(500) NOT NULL,
    file_format VARCHAR(10) NOT NULL, -- 'PDF', 'DOCX'
    file_size_bytes INT NOT NULL,
    file_hash_sha256 CHAR(64) NOT NULL,
    is_primary_active BOOLEAN NOT NULL DEFAULT FALSE,
    parse_status VARCHAR(30) NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'PARSED_SUCCESS', 'PARSE_FAILED', 'USER_MODIFIED'
    raw_extracted_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (resume_id, version_number),
    CHECK (raw_extracted_text IS NULL OR char_length(raw_extracted_text) <= 262144)
);
CREATE INDEX idx_resume_versions_resume_id ON resume_versions(resume_id);
CREATE INDEX idx_resume_versions_hash ON resume_versions(file_hash_sha256);
-- Single active primary resume version per logical resume family:
CREATE UNIQUE INDEX idx_user_primary_resume_version ON resume_versions(resume_id) WHERE is_primary_active = TRUE;

-- 23. resume_evidence_items
CREATE TABLE resume_evidence_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_version_id UUID NOT NULL REFERENCES resume_versions(id) ON DELETE CASCADE,
    ordinal INT NOT NULL,
    category VARCHAR(50) NOT NULL, -- 'EDUCATION', 'EXPERIENCE', 'PROJECTS', 'SKILLS', 'OTHER'
    section_header VARCHAR(150),
    bullet_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (resume_version_id, ordinal),
    CHECK (ordinal >= 0),
    CHECK (category IN ('EDUCATION', 'EXPERIENCE', 'PROJECTS', 'SKILLS', 'OTHER')),
    CHECK (char_length(btrim(bullet_text)) > 0)
);
CREATE INDEX idx_evidence_items_version_id ON resume_evidence_items(resume_version_id);
CREATE INDEX idx_evidence_items_version_ordinal ON resume_evidence_items(resume_version_id, ordinal);

-- 24. resume_evidence_skills
CREATE TABLE resume_evidence_skills (
    evidence_item_id UUID NOT NULL REFERENCES resume_evidence_items(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    parser_confidence NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
    PRIMARY KEY (evidence_item_id, skill_id),
    CHECK (parser_confidence >= 0 AND parser_confidence <= 1)
);
CREATE INDEX idx_evidence_skills_skill ON resume_evidence_skills(skill_id);

-- Phase 8C Candidate Profile is an in-memory read projection; it adds no table.
-- resume_evidence_skills remains parser provenance for one version-scoped evidence item.

-- 25. user_skills (User-Confirmed Claims)
CREATE TABLE user_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    confirmed_by_user BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(30) NOT NULL, -- explicit user-confirmation source (`USER` in current writes)
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_notes VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, skill_id)
);
CREATE INDEX idx_user_skills_user ON user_skills(user_id);
```

`user_skills` is not a destination for parser evidence or project technologies. Phase 8C reads it alongside
`resume_evidence_skills` and `project_skills`, preserving the three source types in an API projection without
adding Candidate Profile persistence or a migration.

---

### 2.5 Job Corpus & Structured Requirements

```sql
-- 26. job_source_records
CREATE TABLE job_source_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_adapter VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source_adapter, external_id),
    CONSTRAINT ck_job_source_adapter_safe CHECK (btrim(source_adapter) <> '' AND source_adapter !~ '[[:cntrl:]]'),
    CONSTRAINT ck_job_source_external_id_safe CHECK (btrim(external_id) <> '' AND external_id !~ '[[:cntrl:]]'),
    CONSTRAINT ck_job_source_url_http CHECK (source_url ~* '^https?://[^[:space:]]+$')
);

-- 27. raw_job_snapshots
CREATE TABLE raw_job_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_source_record_id UUID NOT NULL REFERENCES job_source_records(id) ON DELETE CASCADE,
    raw_payload JSONB NOT NULL,
    payload_hash_sha256 CHAR(64) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (job_source_record_id, payload_hash_sha256),
    CONSTRAINT ck_job_snapshot_hash_sha256 CHECK (payload_hash_sha256 ~ '^[0-9a-f]{64}$')
);

-- 28. normalized_jobs
CREATE TABLE normalized_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_source_record_id UUID NOT NULL UNIQUE REFERENCES job_source_records(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT,
    employment_type VARCHAR(50) NOT NULL, -- 'INTERNSHIP', 'CO_OP', 'FULL_TIME', 'PART_TIME', 'CONTRACT'
    career_level VARCHAR(50) NOT NULL DEFAULT 'UNSPECIFIED', -- 'STUDENT', 'INTERN', 'NEW_GRAD', 'ENTRY_LEVEL', 'EXPERIENCED', 'UNSPECIFIED'
    work_mode VARCHAR(30) NOT NULL DEFAULT 'UNSPECIFIED', -- 'ON_SITE', 'HYBRID', 'REMOTE', 'UNSPECIFIED'
    application_url VARCHAR(1000) NOT NULL,
    current_payload_hash_sha256 CHAR(64),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    posted_at TIMESTAMPTZ,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_normalized_job_application_url_http CHECK (application_url ~* '^https?://[^[:space:]]+$'),
    CONSTRAINT ck_normalized_job_current_hash_sha256 CHECK (current_payload_hash_sha256 IS NULL OR current_payload_hash_sha256 ~ '^[0-9a-f]{64}$')
);
CREATE INDEX idx_normalized_jobs_role_active ON normalized_jobs(role_id, is_active);
CREATE INDEX idx_normalized_jobs_company ON normalized_jobs(company_id);
CREATE INDEX idx_normalized_jobs_discovered ON normalized_jobs(discovered_at);

-- Phase 9 additive migration f3d9a7b1c5e2 adds nullable normalized description text.
-- Phase 10 migration c6f2a8d4b9e1 adds integrity checks for source identity, source/application URLs,
-- and lowercase 64-hex snapshot hashes. Revision e7d1b9f4a2c3 adds the nullable private current snapshot hash.
-- These checks backstop the internal ingestion pipeline.

-- 29. job_industries (Phase 3.1 Delta: Job to Industry Joins)
CREATE TABLE job_industries (
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    industry_id UUID NOT NULL REFERENCES industries(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, industry_id)
);
CREATE INDEX idx_job_industries_industry ON job_industries(industry_id);

-- 30. job_locations
CREATE TABLE job_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    location_id UUID REFERENCES locations(id) ON DELETE SET NULL,
    location_raw VARCHAR(255) NOT NULL
);
CREATE INDEX idx_job_locations_job ON job_locations(job_id);

-- 31. job_skill_requirements
CREATE TABLE job_skill_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    importance VARCHAR(30) NOT NULL, -- source-provided vocabulary; no enum/check constraint (Phase 9 fixtures use 'REQUIRED' and 'PREFERRED')
    description TEXT,
    UNIQUE (job_id, skill_id)
);
CREATE INDEX idx_job_skill_reqs_lookup ON job_skill_requirements(skill_id, job_id);

-- 32. job_education_requirements
CREATE TABLE job_education_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    degree_level VARCHAR(50) NOT NULL,
    target_grad_start DATE,
    target_grad_end DATE
);
CREATE INDEX idx_job_education_reqs_job ON job_education_requirements(job_id);

-- 33. job_eligibility_requirements
CREATE TABLE job_eligibility_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    requirement_type VARCHAR(50) NOT NULL, -- source-provided vocabulary; no enum/check constraint (Phase 9 fixtures use 'WORK_AUTHORIZATION')
    value VARCHAR(100) NOT NULL,
    description TEXT,
    source_evidence TEXT
);
CREATE INDEX idx_job_eligibility_reqs_job ON job_eligibility_requirements(job_id);
```

---

### 2.6 Evaluations & Application Tracker

```sql
-- 34. resume_evaluations
CREATE TABLE resume_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resume_version_id UUID NOT NULL REFERENCES resume_versions(id) ON DELETE CASCADE,
    evaluation_type VARCHAR(50) NOT NULL, -- 'GENERAL_QUALITY', 'ROLE_ALIGNMENT', 'JOB_ALIGNMENT', 'BULLET_ANALYSIS'
    target_role_id UUID REFERENCES roles(id) ON DELETE SET NULL,
    target_job_id UUID REFERENCES normalized_jobs(id) ON DELETE SET NULL,
    rubric_version VARCHAR(50) NOT NULL,
    overall_score SMALLINT NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    category_scores JSONB NOT NULL,
    itemized_reasons TEXT[] NOT NULL,
    suggested_improvements TEXT[] NOT NULL,
    bullet_analysis_detail JSONB,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_evaluations_resume_version ON resume_evaluations(resume_version_id);

-- 35. applications
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_id UUID NOT NULL REFERENCES normalized_jobs(id) ON DELETE CASCADE,
    resume_version_id UUID REFERENCES resume_versions(id) ON DELETE SET NULL, -- Soft reference to protect user deletion rights
    resume_title_snapshot VARCHAR(150),
    resume_hash_snapshot CHAR(64),
    current_status VARCHAR(50) NOT NULL, -- 'SAVED', 'PREPARING', 'APPLIED', 'ONLINE_ASSESSMENT', 'INTERVIEW', 'OFFER', 'REJECTED', 'WITHDRAWN'
    version INT NOT NULL DEFAULT 1 CHECK (version >= 1), -- Optimistic concurrency control
    applied_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,
    next_follow_up_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, job_id)
);
CREATE INDEX idx_applications_user_status ON applications(user_id, current_status);
CREATE INDEX idx_applications_user_followup ON applications(user_id, next_follow_up_at);

-- 36. application_status_histories
CREATE TABLE application_status_histories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    previous_status VARCHAR(50),
    new_status VARCHAR(50) NOT NULL,
    rejection_stage VARCHAR(50), -- 'AFTER_APPLICATION', 'AFTER_OA', 'AFTER_INTERVIEW', 'POSITION_CLOSED', 'UNKNOWN', 'OTHER'
    notes TEXT,
    transitioned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_app_history_app_transitioned ON application_status_histories(application_id, transitioned_at);
```

---

## 3. R2 Executable Baseline and Verification

The pre-production revision `aba441bbcc36` was corrected directly with explicit owner confirmation that it had never been deployed to a non-disposable environment. Its revision ID is unchanged. A database created from the earlier revision body is **not** brought up to date by running `upgrade head`: recreate that explicitly disposable database first. Never stamp an old schema as correct. If any non-disposable deployment is discovered, preserve it and use a reviewed forward migration instead.

### PostgreSQL representation

- IDs and foreign keys use native PostgreSQL `UUID` and Python `uuid.UUID`; API IDs remain JSON strings, now documented as UUIDs in OpenAPI.
- Event timestamps use `TIMESTAMPTZ` and aware Python UTC datetimes. `DATE` remains appropriate for calendar dates. PostgreSQL stores instants; displayed offsets depend on the connection timezone.
- `raw_job_snapshots.raw_payload`, `resume_evaluations.category_scores`, and `resume_evaluations.bullet_analysis_detail` use `JSONB`.
- Preference mode/type lists and evaluation reason/improvement lists use the documented `TEXT[]`. Canonical relationships remain relational foreign keys and join tables.
- The DDL defaults above are server defaults, so raw SQL inserts receive them as well. Python defaults additionally make ORM inserts convenient. `updated_at` has an ORM `onupdate` hook, not a database trigger: direct SQL updates must set it explicitly.
- The documented employment rule remains exactly `currently_employed = TRUE OR end_date IS NOT NULL`; R2 does not introduce a stronger product rule.
- R3 removes `idx_user_sessions_lookup`: the unique index backing `UNIQUE(session_token_hash)` already serves session equality lookup. It also removes the unused `ix_user_sessions_expires_at`; expiry is checked on the row located by its token, and no expiry-scan/cleanup job exists. `idx_user_sessions_user` is retained to support the user foreign key and account-owned session deletion. Models and the same pre-production baseline are updated together.
- `last_seen_at` remains initialized when a session is created but is not updated on authenticated reads. `expires_at` is absolute and is never extended by reads. Any future throttled activity updates or expiration cleanup require a separately scoped change.

### Safe integration testing

Integration tests require PostgreSQL **16** and an explicitly disposable database whose name matches `studentsuccessful_test_[a-z0-9_]+`. Both `TEST_DATABASE_URL` and `ALLOW_DISPOSABLE_TEST_DATABASE=1` must be supplied. `DATABASE_URL` alone is never accepted as a test target; `APP_ENV=production` is rejected before application imports. Naming and opt-in are safety checks, not a substitute for selecting the correct disposable database.

Create a new empty test database on your local PostgreSQL 16 server, then run from the repository root (PowerShell):

```powershell
createdb -h localhost -U postgres studentsuccessful_test_local
$env:TEST_DATABASE_URL = 'postgresql+psycopg2://postgres:postgres@localhost:5432/studentsuccessful_test_local'
$env:ALLOW_DISPOSABLE_TEST_DATABASE = '1'
$env:DATABASE_URL = $env:TEST_DATABASE_URL
$env:DATABASE_MIGRATION_URL = $env:TEST_DATABASE_URL
$env:APP_ENV = 'test'
python -m alembic -c backend/alembic.ini upgrade head
python -m alembic -c backend/alembic.ini current --check-heads
python -m alembic -c backend/alembic.ini check
python -m pytest backend/tests
ruff check backend
```

CI provides a fresh PostgreSQL 16 service and runs this migration/schema verification before the full backend suite. Pytest explicitly replaces both `DATABASE_URL` and `DATABASE_MIGRATION_URL` with the validated disposable `TEST_DATABASE_URL` before application imports, so a local managed-database `.env` cannot redirect tests or test migrations. Tests never call `Base.metadata.create_all()` or `drop_all()`. Ordinary tests use a transaction with session savepoints, so explicit service commits can be tested without persisting their rows. The fresh-migration test uses an empty schema and transactional DDL rollback. The concurrent-registration test needs separate committed transactions and deletes only its uniquely generated account afterward.

Do not use these tests against a development database containing data you want to keep. No reset/delete command for an existing database is automated by R2.


## Phase 6C migration behavior

Accepted chain: `aba441bbcc36` → `b61f0a2c9d34` → `c72e4b9d103f`.
Education is directly 1:N per user; no ApplicationProfile row is required. Native GPA value/scale
are both NUMERIC(5,2), optional as a complete pair, without conversion. The disclosure flag requires
that pair. New records default to non-primary; a partial unique index allows at most one explicit
primary per user. API mutations lock the owner row and coordinate demotion in one transaction.

The new revision preserves valid existing facts. Invalid legacy GPA/date states or duplicate primary
rows block the transaction; it does not repair facts or select a primary. Investigate and obtain the
owner's explicit correction before retrying. Downgrade locks the table and deliberately refuses GPA
values above 99.99 before narrowing precision; no truncation, rounding or deletion is performed.
PostgreSQL NUMERIC itself can round excess fractional digits on direct SQL writes; the API rejects
excess precision before writing, as verified by tests. Applications must use the validated API.


## Phase 6D Employment

Migration `d83f5ca21460` follows `c72e4b9d103f` and adds only ck_employment_date_order.
The existing ck_employment_end_date rule remains: current=false requires an end date;
current=true permits either null or a known end date. A present end date must be >= start date.
Upgrade preserves valid rows and fails transactionally for reversed legacy dates without repairing
facts. Downgrade drops only the new constraint and retains rows and the original rule.

Employment is directly 1:N per User, independent of ApplicationProfile. PATCH/DELETE lock only the
record selected by ID plus authenticated owner; POST does not serialize the User aggregate.


## Phase 6E migration and factual integrity

Revision `e94a6db32571` follows `d83f5ca21460`. Adds only `ck_work_authorization_country_code` and `ck_work_authorization_status` on work_authorizations. Existing uniqueness and all other tables are unchanged. Valid legacy rows retain exact values. Malformed country codes or unsupported statuses block upgrade transactionally, leaving facts and the previous revision unchanged. There is no normalization or legal mapping in the migration. Downgrade drops only the two new checks, preserving rows including new generic categories because the prior column was unconstrained VARCHAR(50).

Work Authorization is one-to-many per User, with exactly one record per user/country and no ApplicationProfile prerequisite. Country identifies the authorization jurisdiction, not residence, nationality or desired job location. API normalization trims and uppercases exactly two ASCII letters; neither API nor database claims ISO membership validation.

The structured statuses are CITIZEN, PERMANENT_RESIDENT, STUDENT_WORK_AUTHORIZATION, TEMPORARY_WORK_AUTHORIZATION, OTHER, STUDENT_VISA_CPT_OPT and WORK_VISA. Phase 6E adds the two generic authorization choices while retaining every baseline value unchanged. CPT/OPT is explicitly a US-specific legacy label; WORK_VISA is a retained legacy label. These are user-selected categories, not determinations of legal eligibility. No legacy facts are mapped or reinterpreted, and no legal equivalence is asserted.

Current and future sponsorship are independent explicit booleans. Status never sets sponsorship, and sponsorship never sets status. Notes are optional factual text, trimmed, limited to 255 characters; blank/null clears. Do not enter government document numbers. Nothing is inferred from notes, location, profile, education, employment or external sources. No job compatibility is computed.

last_confirmed_at is server-managed UTC: set on POST and refreshed on successful PATCH containing at least one editable fact, even if its value is unchanged. GET and empty PATCH preserve the timestamp. The UI sends only changed facts, so an unchanged form closes without reconfirming. Clients cannot supply IDs, ownership or timestamps.


## Phase 6F migration: explicit preference choices

Revision `fa5b7ec43682` follows `e94a6db32571`. Adds only `ck_preferences_work_modes`, `ck_preferences_employment_types`, and `ck_custom_preference_type`. Arrays permit empty selections and only their approved values, without NULL elements or multiple dimensions. The existing user uniqueness, canonical foreign keys/join primary keys, and custom normalized uniqueness remain unchanged. SQLAlchemy and Alembic definitions agree. Incompatible legacy choices fail upgrade transactionally, preserving facts and the previous revision. No repair or taxonomy seeds. Downgrade drops only these checks and preserves rows.

Career Preferences are explicit desired choices, separate from Profile, Education, Employment, Work Authorization and resume evidence. Technology interests use Skill/UserPreferredSkill only and do not create UserSkill or capability claims. No preferences are inferred.

GET `/api/v1/preferences` is authenticated, returns a deterministic complete selection object (empty arrays when unsaved), and creates no row. PUT on the same route is authenticated, requires the current session CSRF token, and replaces the full aggregate: role_ids, industry_ids, location_ids, company_ids, skill_ids, work_modes, employment_types and custom_values. Omitted arrays mean empty and remove previous selections. Success responses use no-store; body/query user_id is rejected. IDs are UUIDs; duplicate canonical IDs and structured choices are deduplicated and sorted. Unknown IDs return controlled 422 before any replacement.

Work modes: ON_SITE, HYBRID, REMOTE. Employment types: INTERNSHIP, CO_OP, NEW_GRAD, PART_TIME. Custom entries have preference_type ROLE/INDUSTRY/LOCATION/COMPANY/SKILL and display value (nonblank, maximum 150 characters). Display text is preserved exactly. Normalized uniqueness uses whitespace collapse/trim plus Unicode casefold, with a maximum normalized length of 150. Duplicate normalized values within a type are rejected; matching values in different types are allowed. Custom entries never become canonical taxonomy entries, even when their labels match.

The service locks the existing User row for aggregate replacement, validates all canonical IDs (with key-share locks against concurrent deletion), then updates the root, joins and custom values in one transaction and commits once. Identical PUT preserves existing root/custom row IDs and timestamps. GET takes a shared User-row lock for a coherent multi-table read. Repository methods never commit. Different users are independent.

Catalog endpoints are authenticated read-only GETs and require no CSRF. Roles support q and active (default true; false returns inactive roles). Skills support q/category and return active skills. Companies support q. Locations support country_code (case-insensitive two-letter filter) and q over city/state-province. Industries have no filters. Search is literal case-insensitive substring, not wildcard input. Names sort case-insensitively then by ID; locations sort country, case-insensitive city, state/province, ID. No catalog mutations are exposed. Existing inactive canonical IDs remain valid preferences; selected items missing from active catalogs stay visible as removable saved IDs in the form.

The `/preferences` form loads catalogs from these APIs, supports multiple selections and explicit Other entries, and saves one complete PUT. New installations have no seeded canonical catalog: empty catalog messaging and custom values are supported. Browser verification fixtures are disposable and are never seeded by migrations. Phase 6G and matching remain deferred.
