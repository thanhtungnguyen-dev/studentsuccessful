# StudentSuccessful — System Architecture Specification (Phase 2 Approved Baseline)

**Document Version:** 1.1 (Approved Baseline)  
**Phase:** SDLC Phase 2 — System Architecture  
**Status:** Approved by Mentee & Mentor  
**Date:** September 5, 2026  

---

## 1. Architectural Principles & Philosophy

StudentSuccessful is architected as a **Clean Modular Monolith** (Next.js frontend, FastAPI backend, PostgreSQL relational database). It adheres to strict dependency layering and clean boundary rules:

```text
                     BROWSER
                       │
                    HTTPS
                       │
                       ▼
                 Next.js / React
                       │
                 Typed API Client (OpenAPI Generated)
                       │
                       ▼
                 /api/v1/*
                       │
              Authentication Boundary (Context Injection)
                       │
                       ▼
                  FastAPI Router
                       │
                       ▼
                 Service Layer
                       │
                 Unit of Work
              ┌────────┼────────┐
              ▼        ▼        ▼
          Domain     Repos    Adapters
          Engines      │        │
              │        │        ├── StorageAdapter (Local / S3)
              │        │        ├── JobSourceAdapter / SourceAdapterRegistry
              │        │        └── AIProvider [later]
              │        │
              │        ▼
              │    PostgreSQL
              │
              └── Pure deterministic logic
```

### Key Architectural Invariants:
1. **Separation of Concerns:**
   - **Routers (`app/api/v1/`):** HTTP translation, schema validation, injecting request correlation IDs and user context. Zero business logic or raw SQL.
   - **Services (`app/services/`):** Use-case orchestration and business rules. Manages multi-repository transactions via a **Unit of Work**.
   - **Domain Engines (`app/domain/`):** Pure, deterministic business algorithms (`MatchingEngine`, `RubricEvaluator`, `ApplicationStateMachine`). Zero database or framework dependencies.
   - **Repositories (`app/repositories/`):** Encapsulate SQLAlchemy queries and joins. Never execute independent `commit()` calls.
   - **Adapters (`app/adapters/`):** Abstract external systems, including `StorageAdapter` implementations and
     the internal `SourceAdapter` contract selected by `SourceAdapterRegistry`.
2. **Candidate Profile preserves source meaning:**
   - `CandidateProfileService` is a read-only projection over explicit facts, project technologies, confirmed
     `UserSkill` rows, and version-scoped `ResumeEvidenceSkill` citations.
   - It reconciles catalog skills by exact ID while retaining separate confirmed, resume-evidence, and project
     sources. It does not create capability states, infer proficiency, or mutate a source record.
3. **Shared Job browsing is separate from Candidate Profile:**
   - Phase 9 reads active normalized jobs and explicit posting requirements for any authenticated user. Jobs have
     no user ownership, and the read path never joins candidate, resume, application, evaluation, or matching data.
   - Raw ingestion snapshots and source provenance remain internal. Job description and requirement text is
     untrusted data, rendered as text by the UI.
   - Phase 10 ingestion is internal-only: an adapter produces a strict source DTO, a normalizer derives
     canonical whitelisted facts, and the ingestion service and repository write the job corpus. No router or
     public ingestion route participates in that flow.
4. **Candidate fit, resume evaluation, matching, and application tracking remain deferred:**
   - Phase 9 supplies no ranking, fit score, recommendation, evaluation, application workflow, or job mutation.
5. **Read projection has no stale stored state:**
   - There is no Candidate Profile table. A request derives its response from currently owned source rows and
     returns no extracted resume text or managed file metadata.
6. **Concurrency & Compensating Transactions:**
   - Application status transitions are deferred; no transition workflow is exposed.
   - File storage operations use compensating cleanup (deleting uploaded files if database metadata creation fails).

---

## 2. Component Layer Responsibilities

| Layer | Responsibility | Invariants |
|---|---|---|
| **API Routers (`app/api/v1/`)** | HTTP transport, Pydantic validation, injecting correlation ID, returning standard status codes. | No business logic, no SQL, no direct DB commits. |
| **Service Layer (`app/services/`)** | Domain orchestration, calling domain engines, coordinating multi-repository transactions via Unit of Work. | No HTTP objects (`Request`/`Response`). Pure Python domain models. |
| **Domain Engines (`app/domain/`)** | Pure business algorithms: deterministic matching, heuristic parsing, rubric evaluation, state machine checks. | Zero database dependencies. Pure functions: $\text{Input Data} \rightarrow \text{Output DTO}$. |
| **Unit of Work & Repositories (`app/repositories/`)** | Data access layer. Manages database transactions (`commit`/`rollback`) across repositories. | Repositories never commit independently. |
| **Adapters (`app/adapters/`)** | Storage and internal source abstractions (`StorageAdapter`, `SourceAdapterRegistry`, `SourceAdapter`). | Domain depends only on abstract interfaces, not concrete storage paths or source implementations. |

---

## 3. End-to-End Control Flows

### 3.1 Flow 1: Safe File Upload with Compensating Transaction
```text
Client                Router                  ResumeService            StorageAdapter         UnitOfWork / DB
  │                      │                          │                         │                      │
  │ 1. POST /api/v1/resumes                         │                         │                      │
  ├─────────────────────►│                          │                         │                      │
  │                      │ 2. Layered Validation    │                         │                      │
  │                      │    (MIME, ZIP bomb cap)  │                         │                      │
  │                      ├─────────────────────────►│                         │                      │
  │                      │                          │ 3. save_file(stream)    │                      │
  │                      │                          ├────────────────────────►│                      │
  │                      │                          │◄────────────────────────┤                      │
  │                      │                          │ 4. save immutable bytes │                      │
  │                      │                          │ 5. begin transaction    │                      │
  │                      │                          ├───────────────────────────────────────────────►│
  │                      │                          │ 6. insert immutable metadata                   │
  │                      │                          │    [If DB Fails] ───────┼────────┐             │
  │                      │                          │                         │        │ rollback    │
  │                      │                          │                         │        ▼             │
  │                      │                          │ 7. compensate: delete_file()    DB Error       │
  │                      │                          │ 8. commit               │                      │
  │                      │                          ├───────────────────────────────────────────────►│
  │◄─────────────────────┼──────────────────────────┤                                                │
```

### 3.2 Deferred historical flow: Batch Job Recommendation (not implemented)
```text
Client                Router                  RecommendationService    CandidateService        JobRepository / DB
  │                      │                          │                         │                      │
  │ 1. GET /api/v1/jobs/recommended                 │                         │                      │
  ├─────────────────────►│                          │                         │                      │
  │                      │ 2. Load Candidate Profile│                         │                      │
  │                      │    & Active Resume Once  │                         │                      │
  │                      ├─────────────────────────►├────────────────────────►│                      │
  │                      │                          │◄────────────────────────┤                      │
  │                      │                          │ 3. Query Candidate Jobs (SQL pre-filter)       │
  │                      │                          ├───────────────────────────────────────────────►│
  │                      │                          │◄───────────────────────────────────────────────┤
  │                      │                          │ 4. Batch In-Memory Matching (MatchingEngine)   │
  │                      │                          │ 5. Sort & Rank Top Matches                     │
  │◄─────────────────────┼──────────────────────────┤                                                │
```

### 3.3 Flow 3: Read-only Candidate Profile

```text
Client                Router                  CandidateProfileService     Repositories / DB
  |                      |                              |                         |
  | GET /api/v1/profile/candidate                       |                         |
  |--------------------->|                              |                         |
  |                      | session-derived owner        |                         |
  |                      |----------------------------->|                         |
  |                      |                              | read owned source rows  |
  |                      |                              |------------------------>|
  |                      |                              |<------------------------|
  |                      |<-----------------------------| reconcile exact IDs     |
```

### 3.4 Flow 4: Read-only shared Job browse

```text
Client                Router                  JobService                  JobRepository / DB
  |                      |                         |                                |
  | GET /api/v1/jobs/{id}|                         |                                |
  |--------------------->| session required        |                                |
  |                      |------------------------>| read active normalized job     |
  |                      |                         |------------------------------->|
  |                      |                         |<-------------------------------|
  |<---------------------| normalized fields and requirements only             |
```

The service returns no raw job snapshots, source identifiers, candidate facts, applications, scores, or matches.
Inactive and unknown IDs share one 404 response.

### 3.5 Flow 5: Internal Job Ingestion

```text
Internal caller       SourceAdapterRegistry / Adapter       JobIngestionService       Repository / DB
      |                              |                                |                         |
      | source input                 | strict source DTO              |                         |
      |----------------------------->|------------------------------->|                         |
      |                              |                                | reuse source identity   |
      |                              |                                | snapshot canonical facts|
      |                              |                                | normalize and replace   |
      |                              |                                | job requirement rows    |
      |                              |                                |------------------------>|
      |<-----------------------------|<-------------------------------|                         |
```

The source record keeps its original `source_url`. The service snapshots only canonical whitelisted normalized
facts, hashes that snapshot, and reuses source records and duplicate snapshots. An unchanged successful fetch
does not add a snapshot or replace facts, but advances `last_verified_at`.
Each normalized job keeps a private current-snapshot hash, so a historical payload can recur after a later
revision without allowing an old snapshot to suppress the required restoration.
Validation rejects blank or
control-character adapter identifiers and external IDs, non-HTTP(S) or whitespace-containing source/application
URLs, naïve posted timestamps, and hashes other than lowercase 64-hex SHA-256; database checks provide the final
integrity backstop.
This flow has no router or OpenAPI operation, and its source identifiers, raw snapshots, hashes, and provenance
remain outside public DTOs.

### 3.6 Deferred historical flow: Concurrency-Protected Application Transition (not implemented)
```text
Client                Router                  ApplicationService       StateMachine            UnitOfWork / DB
  │                      │                          │                         │                      │
  │ 1. POST /api/v1/applications/{id}/transition    │                         │                      │
  │    { target_status: "APPLIED", version: 2 }     │                         │                      │
  ├─────────────────────►│                          │                         │                      │
  │                      │ 2. Delegate Transition   │                         │                      │
  │                      ├─────────────────────────►│                         │                      │
  │                      │                          │ 3. Enforce Allowed Transition                  │
  │                      │                          ├────────────────────────►│                      │
  │                      │                          │◄────────────────────────┤                      │
  │                      │                          │ 4. Atomic Optimistic Locking UPDATE:           │
  │                      │                          │    UPDATE application                          │
  │                      │                          │    SET status = 'APPLIED', version = version + 1
  │                      │                          │    WHERE id = ? AND version = 2                │
  │                      │                          ├───────────────────────────────────────────────►│
  │                      │                          │    [If 0 rows updated: 409 Conflict]           │
  │                      │                          │ 5. Insert ApplicationStatusHistory             │
  │                      │                          │ 6. Commit                                      │
  │◄─────────────────────┼──────────────────────────┤                                                │
```


## 4. R3 Authentication and Session Boundary

Registration/login first validate the browser-facing Origin, then verify/create the user and generate independent random 256-bit session and CSRF tokens. The service commits only SHA-256 digests to `user_sessions`. The router sets an HttpOnly session cookie and a readable `ss_csrf` cookie; both are host-only, SameSite=Lax, Path=/ and Secure in production. Passwords remain Argon2id hashes; no global CSRF HMAC secret or JWT is used.

```text
Browser mutation: read ss_csrf → X-CSRF-Token
    → authenticate opaque session cookie by its digest
    → reject expired/revoked/inactive sessions
    → SHA256(header) → hmac.compare_digest(stored CSRF digest)
    → service mutation → explicit UnitOfWork.commit()
```

Logout uses this boundary on the real route, commits revocation, and clears both cookies. Authentication reads use no commit and do not update activity, expiry, or CSRF state. Every tab sharing a session uses the same stable CSRF value; a new session gets a new pair. The former mutating GET CSRF endpoint is removed. Losing the readable cookie requires a new login, not reconstruction from the stored hash.

Before a session exists, login/register require a matching configured Origin in production. The same-origin Next.js proxy must preserve the original browser Origin; internal backend Host headers are not trusted to establish frontend origin. This protects against browser login-CSRF submissions. Non-production clients can omit Origin for practical CLI/tests, but foreign origins remain rejected. Auth responses use Cache-Control: no-store; no broader caching or API error redesign is introduced.
