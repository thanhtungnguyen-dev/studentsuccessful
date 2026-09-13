# Candidate fit analysis — Phase 12

The fit view explains which explicit job skill requirements have recorded evidence in the signed-in user's records. It does not estimate hiring outcomes or decide whether to apply.

## Audit and implementation boundary

The existing candidate domain contains user-confirmed catalog skills, project-to-skill links, resume-version evidence links, custom skill text, profile facts, education, employment, authorization declarations, and career preferences. Job records contain catalog skill requirements, education requirements, free-form eligibility values, role/type/work mode, and descriptions.

Only the three existing catalog skill source types have an exact common identity with job skill requirements. Phase 12 evaluates that identity without creating candidate or job facts. Profile contact details, custom text, employment prose, career interests, and job descriptions do not imply skills. Education labels are not a degree equivalence system; eligibility strings are not a jurisdiction-aware authorization policy. Those requirements remain unknown.

## Deterministic rules

1. Load the active shared job. Missing and inactive jobs both return the existing safe 404.
2. Load only catalog skill sources owned by the authenticated session user.
3. Compare each job skill requirement's skill ID with candidate skill IDs. Never compare names, substrings, aliases, custom text, degrees, roles, preferences, or prose.
4. A skill with at least one source appears under matched recorded references. Keep every source citation; duplicate evidence does not create duplicate requirements.
5. A skill without a source appears under missing recorded evidence. This means the records contain no evidence, not that the user lacks the ability.
6. Every education and eligibility requirement appears under unknown, with a reason. These categories are neither satisfied nor rejected automatically.

Matching a skill reference does not establish proficiency, recency, years of experience, certification, or any extra conditions in the requirement description. Requirement importance is displayed as catalog data, never converted into a weight. There is no numeric score, percentage, hiring prediction, suitability ranking, or recommendation.

## Provenance

- `CONFIRMED_BY_USER`: a catalog skill explicitly confirmed by the user. This is a declaration, not independent verification.
- `RESUME_EVIDENCE`: a catalog skill linked by parsing to an owned resume evidence item. The response identifies the resume, version, evidence ordinal/category, and parser confidence where present. Confidence describes parser recognition, never ability or probability of being hired.
- `PROJECT`: a catalog skill explicitly linked to an owned project, with the project ID and title. This is recorded project usage, not proof of proficiency.

All stored owned resume versions are included, consistent with the candidate projection. Versions can be historical or non-primary; successfully extracted evidence can also survive a later failed parse. The result must not call that evidence current. No version is silently preferred and evidence is never promoted into a confirmed skill.

## API and privacy

`GET /api/v1/jobs/{id}/fit` derives ownership exclusively from the session. It rejects all query parameters, including `user_id`. Successful and error responses use `Cache-Control: no-store`. The result contains `job_id`, `job_title`, `company_name`, `matched`, `missing`, `unknown`, and `limitations`.

Each requirement contains `category`, `requirement_id`, `name`, `importance`, `description`, `explanation`, `limitation`, and `sources`. For a skill, `requirement_id` is the canonical skill ID (one skill requirement per job); for education and eligibility it is the requirement row ID. The API exposes only the requesting user's selected source citations, never another user's records, resume storage keys, full resume text, raw provider payloads, ingestion hashes, or private provider evidence.

The route delegates to an isolated fit service and repository using the existing UnitOfWork and PostgreSQL queries. Reads are grouped by source type, not repeated per requirement. No fit table, migration, persisted snapshot, write, or background task is needed. Reopening or refreshing the view recomputes the result from current stored records.

## Desktop flow

Open Jobs, select a listing, and choose View fit analysis. The view presents recorded matches and their sources, requirements with no recorded evidence, and unknown requirements with limitations. Loading, errors, retry, expired sessions, and changes of job or account must not expose a stale fit response. Phase 12 introduces no mobile-specific implementation or verification.
