# Phase 6B: Application Profile

## Baseline audit and required schema change

CURRENT MODEL: `application_profiles` already has one row per user, legal and preferred names,
`phone_number`, a combined `address_street`, city/region/postal/country code, and three URL columns.
It has no API/service/repository yet. Database sessions and the generic repository live in
`backend/app/core`, not separate `db` or `repositories` packages. Country codes also occur in the
location model, but there is no independent country taxonomy or country foreign key to reuse.

PROBLEM: Phone, city, region, postal code and country are NOT NULL. Phase 6B explicitly makes
these optional. Requiring invented placeholders would violate the submitted-facts-only rule.

MINIMAL PROPOSED CHANGE: Make only those five columns nullable. Preserve the existing field names,
lengths, unique user ownership, legal first/last name requirements, and separate URL columns.
Street lines remain a single multiline `address_street` value rather than adding duplicate columns.

MIGRATION IMPACT: New revision `b61f0a2c9d34` follows `aba441bbcc36`. Upgrade preserves every existing
value. Downgrade restores NOT NULL and will fail transactionally if optional values have been cleared;
it does not fabricate facts or delete rows. The original baseline is unchanged.

WHY REQUIRED: Users must be able to omit and clear optional contact/address facts without filling
in unrelated information. No other schema changes are part of this phase.

## Implemented contract

Authenticated `GET /api/v1/profile` returns the user's profile, or JSON `null` before the first save.
GET never creates a row. `PATCH /api/v1/profile` creates the first row when legal first and last names
are supplied, or partially updates an existing row. Both names are required by the existing model.
No user ID, profile ID or separate editable email is accepted or returned.

Omitted fields are preserved. Optional fields accept null; blank optional strings become null.
Names/address text are trimmed at their boundaries without restrictions on alphabets. Phone is
trimmed and accepts a modest international-format character set with 5–20 digits; no country is inferred.
Country is an explicitly entered two-letter ASCII code, uppercased; no free-form country mapping or
country-membership taxonomy is introduced. Professional URLs must be absolute http/https URLs with
a host, no whitespace and no embedded credentials; their submitted spelling is otherwise preserved.
Links are not fetched or scraped.

PATCH requires the current session's CSRF header. Ownership comes only from the authenticated user.
The profile repository never commits; the service makes the transaction decision. Writes lock the
owner row to serialize first creation and partial updates. Personal profile responses use no-store.

The `/profile` form checks the existing `/auth/me` provider, loads current facts, and sends only changed
fields. Street address supports both address lines in one multiline input. It shows save/loading/error
states and never pre-fills facts from email, location, links, preferences or resume evidence.

These are **Application Facts**, not Career Preferences: an application address does not set a desired
job location. No preference or resume table is changed.

## Scope and verification waiver

R5 is owner-accepted with its corrected local Playwright lifecycle rerun waived due to Docker Desktop
instability. Phase 6B does not reopen that work, troubleshoot Docker or remove the existing CI E2E.

First Phase 6C prerequisite: change `gpa_value NUMERIC(4,2)` to `NUMERIC(5,2)` with bounded validation,
migration and tests. That change is explicitly deferred.
