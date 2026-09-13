import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { ReviewSections } from "../../components/onboarding/ReviewSections";
import { ReviewPage } from "../../components/onboarding/ReviewPage";
import { useAuth } from "../../components/auth/AuthProvider";
import type { ReviewData } from "./review";
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }) }));
afterEach(() => vi.restoreAllMocks());
const empty: ReviewData = { profile: null, education: [], employment: [], authorization: [], preferences: {}, catalogs: { role_ids: [], industry_ids: [], location_ids: [], company_ids: [], skill_ids: [] } };
const metadata = { id: "row", created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" };
it("renders saved factual fields, zero GPA, false sponsorship and known current end date", () => {
  const data: ReviewData = { ...empty,
    profile: { legal_first_name: "Ada", legal_last_name: "Lovelace", address_street: "First line\nSecond line" },
    education: [{ ...metadata, institution_name: "Example University", major: "Computing", degree_level: "BS", study_year: "YEAR_2", start_date: "2025-01-01", expected_grad_month: 5, expected_grad_year: 2028, gpa_value: "0.00", gpa_scale: "4.00", gpa_include_on_apps: false, is_primary: true }],
    employment: [{ ...metadata, employer_name: "Example Employer", job_title: "Developer", start_date: "2026-01-01", end_date: "2027-05-01", currently_employed: true, description: "<b>Literal facts</b>" }],
    authorization: [{ ...metadata, country_code: "CA", authorization_status: "OTHER", requires_current_sponsorship: false, requires_future_sponsorship: true, last_confirmed_at: "2026-01-01T00:00:00Z" }],
  };
  const html = renderToStaticMarkup(React.createElement(ReviewSections, { data }));
  for (const value of ["Ada", "Lovelace", "Second line", "Example University", "0.00 / 4.00", "2028-05", "Developer", "2027-05-01", "Last confirmed (UTC)", "&lt;b&gt;Literal facts&lt;/b&gt;"])expect(html).toContain(value);
  expect(html).toContain("<dd>No</dd>");expect(html).toContain("<dd>Yes</dd>");expect(html).not.toContain("<b>Literal facts</b>");
});
it("renders all empty optional sections and Edit links", () => {
  const html = renderToStaticMarkup(React.createElement(ReviewSections, { data: empty }));
  for (const text of ["No profile saved", "No education records", "No employment records", "No work authorization records", "No selections saved"])expect(html).toContain(text);
  for (const href of ["/profile", "/education", "/employment", "/work-authorization", "/preferences"])expect(html).toContain(`href="${href}"`);
});
it("resolves preferences, preserves custom text and shows unavailable labels without inventing claims", () => {
  const data: ReviewData = { ...empty, preferences: { role_ids: ["role"], skill_ids: ["missing"], work_modes: ["REMOTE"], employment_types: ["CO_OP"], custom_values: [{ preference_type: "SKILL", value: "  Rust interest  " }] }, catalogs: { ...empty.catalogs, role_ids: [{ id: "role", name: "Developer", is_active: false }] } };
  const html = renderToStaticMarkup(React.createElement(ReviewSections, { data }));
  for (const text of ["Developer", "label unavailable", "missing", "REMOTE", "CO OP", "  Rust interest  ", "(custom)", "not skill claims"])expect(html).toContain(text);
});
it("protects unauthenticated review access", () => {
  vi.mocked(useAuth).mockReturnValue({ user: null, error: "", refresh: vi.fn() });
  const html = renderToStaticMarkup(React.createElement(ReviewPage));expect(html).toContain('href="/login"');expect(html).not.toContain("Complete onboarding");
});
it("shows session loading and failure without private data", () => {
  vi.mocked(useAuth).mockReturnValue({ user: undefined, error: "", refresh: vi.fn() });expect(renderToStaticMarkup(React.createElement(ReviewPage))).toContain("Checking your session");
  vi.mocked(useAuth).mockReturnValue({ user: undefined, error: "Session unavailable", refresh: vi.fn() });const html = renderToStaticMarkup(React.createElement(ReviewPage));expect(html).toContain("Retry session");expect(html).toContain("Session unavailable");
});
it("shows review loading with completion disabled until data arrives", () => {
  vi.mocked(useAuth).mockReturnValue({ user: { id: "owner", email: "owner@example.com" } as NonNullable<ReturnType<typeof useAuth>["user"]>, error: "", refresh: vi.fn() });
  const html = renderToStaticMarkup(React.createElement(ReviewPage));expect(html).toContain("Loading saved onboarding information");expect(html).toMatch(/<button[^>]*disabled=""[^>]*>Complete onboarding/);
});
