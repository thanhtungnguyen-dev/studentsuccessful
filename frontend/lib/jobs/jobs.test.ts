import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  JobDetail,
  JobDetailFailure,
  JobSearchControls,
  JobsContent,
  JobsPage,
  SavedSearchControls,
  fromSavedSearchCriteria,
  readJobDiscoverySearch,
  serializeJobDiscoverySearch,
  toJobSearchParams,
  toSavedSearchCriteria,
  type JobDiscoverySearch,
  type JobsContentProps,
} from "../../components/jobs/JobsPage";
import {
  ApiClient,
  type CurrentUser,
  type PublicJob,
  type PublicJobDetail,
  type PublicJobSearch,
  type SavedJobSearch,
} from "../api/client";

const authState = vi.hoisted(() => ({ user: undefined as CurrentUser | null | undefined, error: "" }));
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: () => ({ ...authState, refresh: vi.fn() }) }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  authState.user = undefined;
  authState.error = "";
});

const job = {
  id: "job-one",
  title: "Backend Software Engineer Intern",
  description: "Build <b>reliable</b> systems\nwith deterministic filters.",
  company_id: "company",
  company_name: "Example Co",
  role_id: "role",
  role_name: "Backend",
  employment_type: "INTERNSHIP",
  career_level: "ENTRY",
  work_mode: "HYBRID",
  source_name: "Greenhouse",
  application_url: "https://example.com/apply",
  posted_at: null,
  discovered_at: "2026-09-10T00:00:00Z",
  first_seen_at: "2026-09-10T00:00:00Z",
  last_seen_at: "2026-09-10T00:00:00Z",
  last_verified_at: "2026-09-10T00:00:00Z",
  canonical_updated_at: "2026-09-10T00:00:00Z",
  lifecycle: "NEW",
  saved: false,
  hidden: false,
  viewed_at: null,
  unseen: true,
  matched_filters: ["Role: Backend", "Country: CA", "Job type: Internship"],
  locations: ["Toronto, ON"],
  skill_requirements: [{ skill_id: "skill", skill_name: "Python", skill_category: "TECHNOLOGY", importance: "REQUIRED", description: "Used for APIs" }],
  education_requirements: [{ id: "education", degree_level: "BS", target_grad_start: null, target_grad_end: "2028-05-01" }],
  eligibility_requirements: [{ id: "eligibility", requirement_type: "WORK_AUTHORIZATION", value: "CA", description: "Eligible to work" }],
} as PublicJobDetail;
const listJob: PublicJob = job;
const search: JobDiscoverySearch = {
  roles: [],
  countries: [],
  regions: [],
  cities: [],
  job_types: [],
  work_modes: [],
  recency: "all",
  keyword: "",
  company: "",
  requirement: "",
  view: "all",
  page: 1,
};
const page: PublicJobSearch = { items: [listJob], page: 1, page_size: 10, total: 1, total_pages: 1 };
const signedInUser: CurrentUser = {
  id: "owner", email: "owner@example.com", is_active: true, created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: "2026-09-10T00:00:00Z",
};
const savedSearch: SavedJobSearch = {
  id: "saved-one",
  name: "Canada Backend Internships",
  criteria: {
    roles: ["backend"],
    countries: ["CA"],
    regions: [],
    cities: [],
    job_types: ["INTERNSHIP"],
    work_modes: ["REMOTE", "HYBRID"],
    recency: "24h",
    keyword: null,
    company: null,
    requirement: null,
  },
  alert_mode: "OFF",
  alert_enabled_at: null,
  created_at: "2026-09-10T00:00:00Z",
  updated_at: "2026-09-10T00:00:00Z",
};

function response(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

function renderJobsContent(overrides: Partial<JobsContentProps> = {}) {
  return render(h(JobsContent, {
    result: page,
    error: "",
    search,
    selected: listJob.id,
    detail: job,
    detailError: null,
    pendingJobIds: new Set<string>(),
    selectJob: vi.fn(),
    changePage: vi.fn(),
    clearFilters: vi.fn(),
    retryJobs: vi.fn(),
    retryDetail: vi.fn(),
    toggleSave: vi.fn(),
    toggleHide: vi.fn(),
    ...overrides,
  }));
}

it("uses no-store URLs with repeated structured filters and a current CSRF token", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce(response(page))
    .mockResolvedValueOnce(response({ job_id: "job-one", saved: true, hidden: false, viewed_at: null, unseen: true }))
    .mockResolvedValueOnce(response([savedSearch]))
    .mockResolvedValueOnce(response(savedSearch, 201))
    .mockResolvedValueOnce(response(null, 204));
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("document", { cookie: "ss_csrf=first" });
  const client = new ApiClient();

  await client.listJobs({
    role: ["backend", "platform"],
    country: ["CA"],
    job_type: ["INTERNSHIP"],
    work_mode: ["REMOTE", "HYBRID"],
    recency: "24h",
    page: 2,
    page_size: 10,
    sort: "newest",
  });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs?role=backend&role=platform&country=CA&job_type=INTERNSHIP&work_mode=REMOTE&work_mode=HYBRID&recency=24h&page=2&page_size=10&sort=newest",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }),
  );
  await client.updateJobState("job one", { saved: true });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20one/state",
    expect.objectContaining({
      method: "PATCH",
      body: '{"saved":true}',
      headers: { "Content-Type": "application/json", "X-CSRF-Token": "first" },
      credentials: "same-origin",
      cache: "no-store",
    }),
  );
  await client.listSavedSearches();
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/saved-searches", expect.objectContaining({ method: "GET", cache: "no-store" }));
  await client.createSavedSearch({
    name: savedSearch.name,
    criteria: savedSearch.criteria,
    alert_mode: "OFF",
  });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/saved-searches",
    expect.objectContaining({ method: "POST", headers: { "X-CSRF-Token": "first", "Content-Type": "application/json" } }),
  );
  await client.deleteSavedSearch(savedSearch.id);
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/saved-searches/saved-one",
    expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "first" } }),
  );
});

it("serializes active filters into the URL and restores exact saved criteria", () => {
  const active: JobDiscoverySearch = {
    roles: ["backend", "platform"],
    countries: ["CA"],
    regions: ["Ontario"],
    cities: ["Toronto"],
    job_types: ["INTERNSHIP"],
    work_modes: ["REMOTE", "HYBRID"],
    recency: "24h",
    keyword: "python",
    company: "Acme",
    requirement: "PostgreSQL",
    view: "saved",
    page: 2,
  };
  const query = serializeJobDiscoverySearch(active);
  expect(query).toBe("role=backend&role=platform&country=CA&region=Ontario&city=Toronto&job_type=INTERNSHIP&work_mode=REMOTE&work_mode=HYBRID&keyword=python&company=Acme&requirement=PostgreSQL&recency=24h&view=saved&page=2");
  expect(readJobDiscoverySearch("?" + query)).toEqual(active);
  expect(toJobSearchParams(active)).toEqual({
    role: ["backend", "platform"],
    country: ["CA"],
    region: ["Ontario"],
    city: ["Toronto"],
    job_type: ["INTERNSHIP"],
    work_mode: ["REMOTE", "HYBRID"],
    recency: "24h",
    keyword: "python",
    company: "Acme",
    requirement: "PostgreSQL",
    view: "saved",
    page: 2,
    page_size: 10,
    sort: "newest",
  });
  const criteria = toSavedSearchCriteria(active);
  expect(criteria).not.toHaveProperty("view");
  expect(fromSavedSearchCriteria(savedSearch.criteria)).toEqual({
    ...search,
    roles: ["backend"],
    countries: ["CA"],
    job_types: ["INTERNSHIP"],
    work_modes: ["REMOTE", "HYBRID"],
    recency: "24h",
  });
});

it("rejects malformed URL choices while retaining a safe filter-first default", () => {
  expect(readJobDiscoverySearch("?role=bad%2Frole&country=canada&job_type=UNKNOWN&work_mode=AI&recency=forever&view=all&page=zero")).toEqual(search);
});

it("renders the primary filters, secondary filters, and no recommendation language", () => {
  const html = render(h(JobSearchControls, {
    draft: { ...search, roles: ["backend"], countries: ["CA"], job_types: ["INTERNSHIP"] },
    roles: [{ id: "role", name: "Backend", slug: "backend", is_active: true }],
    locations: [{ id: "location", country_code: "CA", state_province: "Ontario", city: "Toronto" }],
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onClear: vi.fn(),
  }));
  for (const text of ["Filters", "Role", "Location", "Job type", "Work mode", "Recency", "More filters", "Keywords", "Skill or technology", "Apply filters", "Clear filters"]) {
    expect(html).toContain(text);
  }
  expect(html).not.toMatch(/recommended|candidate fit|match percentage|AI explanation/i);
});

it("renders concise canonical cards with filter explanations and state actions", () => {
  const html = renderJobsContent();
  for (const value of [
    "Newest matching jobs", "Backend Software Engineer Intern", "Example Co", "HYBRID", "INTERNSHIP",
    "Unseen", "NEW", "Matched your filters: Role: Backend · Country: CA · Job type: Internship",
    "Apply", "Details", "Save", "Hide",
  ]) expect(html).toContain(value);
  expect(html).not.toMatch(/source adapter|external id|source url|snapshot|hash|recommendation/i);
});

it("renders saved-search operations without a separate tracking subsystem", () => {
  const html = render(h(SavedSearchControls, {
    searches: [savedSearch],
    name: "",
    error: "",
    onNameChange: vi.fn(),
    onCreate: vi.fn(),
    onOpen: vi.fn(),
    onUpdateCriteria: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
    onAlertModeChange: vi.fn(),
    onRetry: vi.fn(),
  }));
  for (const value of ["Saved searches", "Save current search", savedSearch.name, "Alerts", "Off", "Instant", "Hourly digest", "Daily digest", "Open", "Update filters", "Rename", "Delete"]) {
    expect(html).toContain(value);
  }
  expect(html).not.toMatch(/application status|interview|offer/i);
});

it("renders empty, loading, error, pagination, and retry states", () => {
  const empty = renderJobsContent({
    result: { ...page, items: [], total: 0, total_pages: 0 },
    selected: null,
    detail: null,
    search: { ...search, countries: ["CA"] },
  });
  expect(empty).toContain("No active jobs match these filters.");
  expect(empty).toContain("Clear filters");
  expect(renderJobsContent({ result: null, selected: null, detail: null })).toContain("Loading jobs…");
  const failed = renderJobsContent({ result: null, error: "Please try again.", selected: null, detail: null });
  expect(failed).toContain("Retry jobs");
  const paged = renderJobsContent({ result: { ...page, page: 2, total: 23, total_pages: 3 } });
  expect(paged).toContain("Page 2 of 3 · 23 jobs");
  expect(paged).toContain("Previous page");
  expect(paged).toContain("Next page");
});

it("uses a safe direct application link and displays retryable detail failure", () => {
  const html = render(h(JobDetail, { job }));
  expect(html).toContain('href="https://example.com/apply"');
  expect(html).toContain('target="_blank"');
  expect(html).toContain('rel="noopener noreferrer"');
  expect(html).toContain("&lt;b&gt;reliable&lt;/b&gt;");
  expect(html).not.toContain("<b>reliable</b>");
  expect(render(h(JobDetailFailure, { message: "Please try again.", retry: vi.fn() }))).toContain("Retry job details");
});

it("shows authenticated controls while the canonical feed is loading", () => {
  authState.user = signedInUser;
  const html = render(h(JobsPage));
  expect(html).toContain("Filters");
  expect(html).toContain("Loading jobs…");
});
