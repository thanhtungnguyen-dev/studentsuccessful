# StudentSuccessful — Software Requirements Specification (Phase 0 Final Baseline)

**Document Version:** 1.1 (Approved Baseline)  
**Status:** Approved  
**Author:** Senior Software Engineer & Mentor / Mentee  

---

## 1. Product Problem Statement

Undergraduate computer science and software engineering students face a fragmented, inefficient, and error-prone job search process:
1. **Repetitive Application Friction:** Students re-enter the same biographical, educational, legal eligibility, and factual answers across dozens or hundreds of distinct application portals (Workday, Greenhouse, Lever, Taleo).
2. **Disconnect Between Resume & Profile Reality:** Students maintain disparate resume versions and claimed skills, leading to situations where claimed capabilities lack verifiable resume evidence or resume bullet points lack measurable technical depth.
3. **Black-Box Job Matching:** Modern job boards and generic AI tools offer opaque, unexplainable "match percentages" without itemizing hard-constraint eligibility failures (such as work authorization or graduation term mismatch) or specific skill gaps.
4. **Disorganized Lifecycle Management:** Tracking applications across "Saved", "Applied", "Online Assessment", "Interview", and "Offer" relies on ad-hoc spreadsheets, causing missed deadlines, untracked resume versions, and inability to analyze what profiles yield interview callbacks.
5. **Premature & Dangerous Automation:** Existing "auto-apply" tools operate on free-text hallucination or uncontrolled scraping, risking legal misrepresentation on critical compliance questions (e.g., visa sponsorship, clearance) and site bans.

---

## 2. Product Vision

**StudentSuccessful** is an engineering-first, maintainable career and internship platform built to empower students through structured data discipline, explainable matching algorithms, deterministic profile-resume provenance, and an application lifecycle manager.

The platform deliberately decouples:
- **Application Profile** (strictly factual data for application completion)
- **Career Preferences** (taxonomical filtering criteria)
- **Resume Evidence** (parsed text provenance from uploaded documents)
- **Candidate Profile** (reconciled multi-state skill knowledge base)
- **Normalized Job Database** (curated fixtures and verified live opportunities)
- **Explainable Matching Engine** (three-state hard constraints + configurable scoring profiles)
- **Multi-Tier Resume Evaluator** (General Quality, Role Alignment, Job Alignment)
- **Application Tracker** (stateful audit history)

---

## 3. Core Domain Entities & Structural Principles

### 3.1 Strict Separation of Profile vs. Preferences
- **ApplicationProfile:** Strictly factual information used for completing applications (personal, educational, contact, employment history, work eligibility answers, and approved reusable answers).
- **CareerPreferences:** Search and filtering preferences (target roles, industries, target locations, work modes, employment types, preferred companies, and technology interests).
- **Onboarding Discipline:** Skill entry is **not required** during initial onboarding. Skills are discovered via resume parsing and presented to the user for one-click confirmation and editing.

### 3.2 Four-State Candidate Skill Model
Parsed resume content represents *reported evidence*, not verified truth. The Candidate Profile synthesizes claimed profile skills with parsed resume evidence using four mutually exclusive states:
1. **State A (Confirmed + Evidence):** User explicitly confirmed skill AND parsed resume contains supporting evidence.
2. **State B (Confirmed, Missing Evidence):** User confirmed skill BUT resume lacks supporting evidence. Guidance: *"You indicated experience with X, but your active resume does not demonstrate it."*
3. **State C (Evidence Found, Unconfirmed):** Resume parser extracted a candidate skill keyword, but the user has not verified it. (Protects against parser misclassifications, e.g., "Spring Boot" parsed as "Boot").
4. **State D (Missing / Unknown):** Neither user nor resume indicates the skill.

### 3.3 Three-State Hard Constraints
Eligibility evaluations must never assume binary pass/fail when data is incomplete. The system supports:
- **`COMPATIBLE`:** Explicit user facts satisfy explicit job requirements.
- **`INCOMPATIBLE`:** Explicit conflict between user facts and job requirements (e.g., job requires US citizenship; candidate is on F-1 visa).
- **`UNKNOWN`:** Required job constraint is unstated in the posting (e.g., posting does not specify whether sponsorship is available). System prompts: *"Employer sponsorship policy is unstated."*

### 3.4 Configurable Scoring (No Premature Weights)
Matching score is an explainable aggregation of configurable components governed by `RoleScoringProfile` modules (e.g., `BackendInternshipScoringProfile`, `SystemsInternshipScoringProfile`). Hard weights are not locked in Phase 0; they will be calibrated and tested against real job fixtures in Phase 11.

### 3.5 Three-Tier Resume Evaluation
Evaluations represent rubric alignment, never interview or hiring predictions:
1. **General Resume Quality:** Structure, clarity, technical depth, quantifiable impact, readability, and parseability.
2. **Role Alignment:** Alignment against StudentSuccessful's defined role rubrics (Backend SWE vs. Systems SWE vs. ML).
3. **Job Alignment:** Alignment against the specific requirements and skills of a single target posting.
4. **Interactive Bullet Analyzer:** Evaluates single bullets for `Action + Context + Implementation + Outcome` and prompts for missing factual details.

### 3.6 Data Privacy & Sensitive Information
- Sensitive demographic fields (race, ethnicity, gender, disability, veteran status) are **not stored by default** in MVP.
- When future application flows encounter sensitive fields, they are handled via **"Use Once"** by default, with explicit opt-in required to save.
- Core privacy features include granular answer deletion, resume deletion, full data export, and complete account deletion.

### 3.7 Job Data Stratification
- **Development Job Fixtures:** Curated sample postings used for reproducible testing of matching, normalization, and UI.
- **Live Jobs:** Active market postings maintain internal source provenance (`source`, `sourceUrl`, `externalId`), discovery/verification timestamps, and active status. Public job browsing exposes only normalized shared job fields and explicit requirements; it does not expose source provenance or snapshots.

---

## 4. MVP Architecture & Technology Stack
- **Architecture:** Modular Monolith (Next.js frontend, FastAPI backend, PostgreSQL relational database).
- **ORM & Migrations:** SQLAlchemy + Alembic.
- **Validation:** Pydantic models for all API boundaries.
- **Resume Ingestion:** Deterministic extraction (PDF/DOCX text parsing, heuristic section detection, taxonomy dictionary lookup) with interactive user review/correction, and late-stage AI fallback.


## Implemented Phase 6E boundary: Work Authorization

Work Authorization is one-to-many per User, with exactly one record per user/country and no ApplicationProfile prerequisite. Country identifies the authorization jurisdiction, not residence, nationality or desired job location. API normalization trims and uppercases exactly two ASCII letters; neither API nor database claims ISO membership validation.

The structured statuses are CITIZEN, PERMANENT_RESIDENT, STUDENT_WORK_AUTHORIZATION, TEMPORARY_WORK_AUTHORIZATION, OTHER, STUDENT_VISA_CPT_OPT and WORK_VISA. Phase 6E adds the two generic authorization choices while retaining every baseline value unchanged. CPT/OPT is explicitly a US-specific legacy label; WORK_VISA is a retained legacy label. These are user-selected categories, not determinations of legal eligibility. No legacy facts are mapped or reinterpreted, and no legal equivalence is asserted.

Current and future sponsorship are independent explicit booleans. Status never sets sponsorship, and sponsorship never sets status. Notes are optional factual text, trimmed, limited to 255 characters; blank/null clears. Do not enter government document numbers. Nothing is inferred from notes, location, profile, education, employment or external sources. No job compatibility is computed.

last_confirmed_at is server-managed UTC: set on POST and refreshed on successful PATCH containing at least one editable fact, even if its value is unchanged. GET and empty PATCH preserve the timestamp. The UI sends only changed facts, so an unchanged form closes without reconfirming. Clients cannot supply IDs, ownership or timestamps.

Authenticated users may add/edit/delete one record per country at `/work-authorization`, with explicit delete confirmation and persistence after refresh. Work-authorization country is separate from desired job location. Phase 6F Career Preferences, job eligibility evaluation and later features remain unimplemented.
