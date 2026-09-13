"use client";

import Link from "next/link";
import { useEffect, useState, useRef } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type CatalogItem,
  type CatalogLocation,
  type Application,
  type JobSearchParams,
  type JobUserState,
  type JobUserStateUpdate,
  type PublicJob,
  type PublicJobDetail,
  type PublicJobSearch,
  type SavedJobSearch,
  type SavedJobSearchCreate,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { DiscoveryFilters, AppliedFilters, EMPLOYMENT_TYPES, WORK_MODES, RECENCY_OPTIONS } from "./DiscoveryFilters";
import { Skeleton } from "../ui/skeleton";
import { MarkAsApplied } from "../applications/MarkAsApplied";
import { safeApplicationUrl } from "../../lib/jobs/applicationUrl";

export type JobDetailError = { jobId: string; message: string };
export type JobFeedView = "all" | "saved" | "hidden";
export type JobRecency = "1h" | "24h" | "3d" | "7d" | "all";
export type SavedSearchAlertMode = "OFF" | "INSTANT" | "HOURLY_DIGEST" | "DAILY_DIGEST";
export type JobDiscoverySearch = {
  roles: string[];
  countries: string[];
  regions: string[];
  cities: string[];
  job_types: string[];
  work_modes: string[];
  recency: JobRecency;
  keyword: string;
  company: string;
  requirement: string;
  view: JobFeedView;
  page: number;
};
export type JobDiscoveryDraft = Omit<JobDiscoverySearch, "page" | "view">;

const DEFAULT_SEARCH: JobDiscoverySearch = {
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
const ALERT_MODE_OPTIONS: ReadonlyArray<{ value: SavedSearchAlertMode; label: string }> = [
  { value: "OFF", label: "Off" },
  { value: "INSTANT", label: "Instant" },
  { value: "HOURLY_DIGEST", label: "Hourly digest" },
  { value: "DAILY_DIGEST", label: "Daily digest" },
];

function optional(value: string): string | undefined {
  const normalized = value.trim();
  return normalized || undefined;
}

function unique(values: string[]): string[] {
  return [...new Set(values)];
}

function known(values: string[], allowed: readonly string[]): string[] {
  return unique(values.filter((value) => allowed.includes(value)));
}

function roleValues(values: string[]): string[] {
  return unique(values.filter((value) => /^[a-z0-9][a-z0-9-]{0,99}$/i.test(value)).map((value) => value.toLowerCase()));
}

function countryValues(values: string[]): string[] {
  return unique(values.filter((value) => /^[a-z]{2}$/i.test(value)).map((value) => value.toUpperCase()));
}

function textValues(values: string[]): string[] {
  return unique(values.map((value) => value.trim()).filter(Boolean));
}

export function readJobDiscoverySearch(search: string): JobDiscoverySearch {
  const params = new URLSearchParams(search);
  const page = Number(params.get("page") ?? "1");
  const recency = params.get("recency");
  const view = params.get("view");
  return {
    roles: roleValues(params.getAll("role")),
    countries: countryValues(params.getAll("country")),
    regions: textValues(params.getAll("region")),
    cities: textValues(params.getAll("city")),
    job_types: known(params.getAll("job_type"), EMPLOYMENT_TYPES),
    work_modes: known(params.getAll("work_mode"), WORK_MODES),
    recency: RECENCY_OPTIONS.some((option) => option.value === recency) ? recency as JobRecency : "all",
    keyword: params.get("keyword") ?? "",
    company: params.get("company") ?? "",
    requirement: params.get("requirement") ?? "",
    view: view === "saved" || view === "hidden" ? view : "all",
    page: Number.isInteger(page) && page > 0 ? page : 1,
  };
}

function appendValues(params: URLSearchParams, key: string, values: string[]) {
  for (const value of values) params.append(key, value);
}

export function serializeJobDiscoverySearch(search: JobDiscoverySearch): string {
  const params = new URLSearchParams();
  appendValues(params, "role", search.roles);
  appendValues(params, "country", search.countries);
  appendValues(params, "region", search.regions);
  appendValues(params, "city", search.cities);
  appendValues(params, "job_type", search.job_types);
  appendValues(params, "work_mode", search.work_modes);
  for (const [key, value] of Object.entries({
    keyword: optional(search.keyword),
    company: optional(search.company),
    requirement: optional(search.requirement),
  })) if (value) params.set(key, value);
  if (search.recency !== "all") params.set("recency", search.recency);
  if (search.view !== "all") params.set("view", search.view);
  if (search.page !== 1) params.set("page", String(search.page));
  return params.toString();
}

export function toJobSearchParams(search: JobDiscoverySearch): JobSearchParams {
  return {
    role: search.roles,
    country: search.countries,
    region: search.regions,
    city: search.cities,
    job_type: search.job_types,
    work_mode: search.work_modes,
    recency: search.recency,
    keyword: optional(search.keyword),
    company: optional(search.company),
    requirement: optional(search.requirement),
    view: search.view,
    page: search.page,
    page_size: 10,
    sort: "newest",
  };
}

export function toSavedSearchCriteria(search: JobDiscoverySearch): SavedJobSearchCreate["criteria"] {
  return {
    roles: search.roles,
    countries: search.countries,
    regions: search.regions,
    cities: search.cities,
    job_types: search.job_types,
    work_modes: search.work_modes,
    recency: search.recency,
    keyword: optional(search.keyword) ?? null,
    company: optional(search.company) ?? null,
    requirement: optional(search.requirement) ?? null,
  };
}

export function fromSavedSearchCriteria(criteria: SavedJobSearch["criteria"]): JobDiscoverySearch {
  return {
    ...DEFAULT_SEARCH,
    roles: criteria.roles ?? [],
    countries: criteria.countries ?? [],
    regions: criteria.regions ?? [],
    cities: criteria.cities ?? [],
    job_types: criteria.job_types ?? [],
    work_modes: criteria.work_modes ?? [],
    recency: criteria.recency,
    keyword: criteria.keyword ?? "",
    company: criteria.company ?? "",
    requirement: criteria.requirement ?? "",
  };
}

function browserSearch(): JobDiscoverySearch {
  return typeof window === "undefined" ? { ...DEFAULT_SEARCH } : readJobDiscoverySearch(window.location.search);
}

function toDraft(search: JobDiscoverySearch): JobDiscoveryDraft {
  return {
    roles: search.roles,
    countries: search.countries,
    regions: search.regions,
    cities: search.cities,
    job_types: search.job_types,
    work_modes: search.work_modes,
    recency: search.recency,
    keyword: search.keyword,
    company: search.company,
    requirement: search.requirement,
  };
}

function hasFilters(search: JobDiscoverySearch): boolean {
  return Boolean(
    search.roles.length || search.countries.length || search.regions.length || search.cities.length
    || search.job_types.length || search.work_modes.length || search.recency !== "all"
    || search.keyword || search.company || search.requirement,
  );
}

function displayChoice(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function JobMeta({ job }: { job: PublicJob | PublicJobDetail }) {
  return (
    <p className="muted">
      {[job.company_name, job.role_name, job.work_mode ? displayChoice(job.work_mode) : null, job.employment_type ? displayChoice(job.employment_type) : null]
        .filter(Boolean)
        .join(" · ")}
    </p>
  );
}

function formatJobDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(new Date(value));
}

function JobFreshness({ job }: { job: PublicJob | PublicJobDetail }) {
  const date = job.posted_at || job.first_seen_at;
  return <p className="job-freshness muted">{job.unseen ? "Unseen · " : ""}{job.lifecycle === "NEW" ? "New · " : ""}{date ? <time dateTime={date}>{formatJobDate(date)}</time> : "Date not provided"}</p>;
}

export function jobDescriptionSummary(description: string | null): string {
  const value = description?.trim();
  if (!value) return "No description provided.";
  return value.length > 240 ? value.slice(0, 239).trimEnd() + "…" : value;
}

function MatchedFilters({ filters }: { filters: string[] }) {
  if (!filters.length) return null;
  return <p className="job-matched">Matched your filters: {filters.join(" · ")}</p>;
}

type JobActionProps = {
  job: PublicJob | PublicJobDetail;
  onDetails?: () => void;
  onSave?: () => void;
  onHide?: () => void;
  pending?: boolean;
  tracked?: boolean;
  onTracked?: (application: Application) => void;
};

function JobActions({ job, onDetails, onSave, onHide, pending = false, tracked, onTracked }: JobActionProps) {
  const application = safeApplicationUrl(job.application_url);
  return (
    <div className="job-actions">
      {application ? (
        <a className="secondary" href={application} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
          Apply
        </a>
      ) : null}
      <MarkAsApplied canonicalJobId={job.id} jobTitle={job.title} tracked={tracked} onTracked={onTracked} />
      {onDetails ? <button className="secondary" type="button" onClick={onDetails}>Details</button> : null}
      {onSave ? (
        <button className="secondary" type="button" disabled={pending} onClick={onSave}>
          {job.saved ? "Unsave" : "Save"}
        </button>
      ) : null}
      {onHide ? (
        <button className="secondary" type="button" disabled={pending} onClick={onHide}>
          {job.hidden ? "Unhide" : "Hide"}
        </button>
      ) : null}
    </div>
  );
}

export function JobDetail({
  job,
  onSave,
  onHide,
  pending,
  tracked,
  onTracked,
}: {
  job: PublicJobDetail | null;
  onSave?: () => void;
  onHide?: () => void;
  pending?: boolean;
  tracked?: boolean;
  onTracked?: (application: Application) => void;
}) {
  if (!job) {
    return (
      <section className="auth-card dashboard-card">
        <h2>Job details</h2>
        <p className="muted">Select an opportunity to explore the role, requirements, and next steps.</p>
      </section>
    );
  }
  return (
    <section className="auth-card dashboard-card job-detail" aria-label="Selected job details" tabIndex={0} aria-live="polite">
      <h2>{job.title}</h2>
      <JobMeta job={job} />
      <JobFreshness job={job} />
      <MatchedFilters filters={job.matched_filters ?? []} />
      <dl>
        <div><dt>Official source</dt><dd>{job.source_name}</dd></div>
        <div><dt>Locations</dt><dd>{job.locations.length ? job.locations.join(", ") : "Not provided"}</dd></div>
        <div><dt>Posted</dt><dd>{job.posted_at ? formatJobDate(job.posted_at) : "Not provided"}</dd></div>
        <div><dt>First seen</dt><dd>{formatJobDate(job.first_seen_at)}</dd></div>
        <div><dt>Last verified</dt><dd>{formatJobDate(job.last_verified_at)}</dd></div>
      </dl>
      <JobActions job={job} onSave={onSave} onHide={onHide} pending={pending} tracked={tracked} onTracked={onTracked} />
      <h3>About the role</h3>
      <p className="job-description">{job.description || "No description provided."}</p>
      <RequirementList
        title="Skill requirements"
        items={job.skill_requirements.map((item) =>
          [item.skill_name, item.importance, item.description].filter(Boolean).join(" · "),
        )}
      />
      <RequirementList
        title="Education requirements"
        items={job.education_requirements.map((item) =>
          [item.degree_level, item.target_grad_start, item.target_grad_end].filter(Boolean).join(" · "),
        )}
      />
      <RequirementList
        title="Eligibility requirements"
        items={job.eligibility_requirements.map((item) =>
          [item.requirement_type, item.value, item.description].filter(Boolean).join(" · "),
        )}
      />
      <div className="job-detail-links">
        <Link className="secondary" href={"/jobs/" + encodeURIComponent(job.id) + "/fit"}>View fit analysis</Link>
        <Link className="secondary" href={"/jobs/" + encodeURIComponent(job.id) + "/resume-alignment"}>View resume alignment</Link>
        <Link className="secondary" href={"/jobs/" + encodeURIComponent(job.id) + "/gaps"}>View skill gap analysis</Link>
        <Link className="secondary" href={"/jobs/" + encodeURIComponent(job.id) + "/resume-plan"}>View resume improvement plan</Link>
        <Link className="secondary" href={"/jobs/" + encodeURIComponent(job.id) + "/resume-draft"}>View resume tailoring draft</Link>
      </div>
    </section>
  );
}

function RequirementList({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="job-requirements">
      <h3>{title}</h3>
      {items.length ? <ul>{items.map((item, index) => <li key={item + "-" + index}>{item}</li>)}</ul>
        : <p className="muted">{"No " + title.toLowerCase() + " provided."}</p>}
    </section>
  );
}

export function JobDetailFailure({ message, retry }: { message: string; retry: () => void }) {
  return (
    <section className="auth-card dashboard-card">
      <p role="alert" className="auth-error">Could not load job details. {message}</p>
      <button className="secondary" onClick={retry}>Retry job details</button>
    </section>
  );
}

export const JobSearchControls = DiscoveryFilters;

export function FeedViewTabs({ view, onChange }: { view: JobFeedView; onChange: (view: JobFeedView) => void }) {
  return (
    <nav className="job-feed-tabs" aria-label="Job views">
      {(["all", "saved", "hidden"] as const).map((value) => (
        <button
          key={value}
          className="secondary"
          aria-pressed={view === value}
          type="button"
          onClick={() => onChange(value)}
        >
          {displayChoice(value)}
        </button>
      ))}
    </nav>
  );
}

export function SavedSearchControls({
  searches,
  name,
  error,
  onNameChange,
  onCreate,
  onOpen,
  onUpdateCriteria,
  onRename,
  onDelete,
  onAlertModeChange,
  onRetry,
}: {
  searches: SavedJobSearch[] | null;
  name: string;
  error: string;
  onNameChange: (value: string) => void;
  onCreate: () => void;
  onOpen: (search: SavedJobSearch) => void;
  onUpdateCriteria: (search: SavedJobSearch) => void;
  onRename: (search: SavedJobSearch) => void;
  onDelete: (search: SavedJobSearch) => void;
  onAlertModeChange: (search: SavedJobSearch, mode: SavedSearchAlertMode) => void;
  onRetry: () => void;
}) {
  return (
    <section className="saved-searches">
      <h2>Saved searches</h2><p className="muted">Return to a search or save your applied filters.</p>
      <details className="saved-search-create" key={searches?.map((search) => search.id).join(",")}>
        <summary>Save current search</summary>
        <form onSubmit={(event) => { event.preventDefault(); onCreate(); }}>
          <label>Search name<input required value={name} maxLength={100} onChange={(event) => onNameChange(event.target.value)} placeholder="Name this search" /></label>
          <div className="job-actions"><button type="submit">Save</button><button type="button" className="secondary" onClick={(event) => { event.currentTarget.closest("details")?.removeAttribute("open"); onNameChange(""); }}>Cancel</button></div>
        </form>
      </details>
      {error ? (
        <div>
          <p role="alert" className="auth-error">{error}</p>
          <button className="secondary" type="button" onClick={onRetry}>Retry saved searches</button>
        </div>
      ) : searches === null ? <p role="status">Loading saved searches…</p>
        : searches.length ? (
          <ul className="saved-search-list">
            {searches.map((search) => (
              <li key={search.id}>
                <strong>{search.name}</strong>
                <label className="saved-search-alert-mode">
                  Alerts
                  <select
                    aria-label={"Alerts for " + search.name}
                    value={search.alert_mode}
                    onChange={(event) => onAlertModeChange(search, event.target.value as SavedSearchAlertMode)}
                  >
                    {ALERT_MODE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <p className="muted saved-search-alert-help">
                  {search.alert_mode === "OFF"
                    ? "Alerts are off until you enable one."
                    : "Only jobs discovered after activation can alert you."}
                </p>
                <div className="job-actions">
                  <button className="secondary" type="button" onClick={() => onOpen(search)}>Open</button>
                  <button className="secondary" type="button" onClick={() => onUpdateCriteria(search)}>Update filters</button>
                  <button className="secondary" type="button" onClick={() => onRename(search)}>Rename</button>
                  <button className="secondary" type="button" onClick={() => onDelete(search)}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className="muted">No saved searches yet.</p>}
    </section>
  );
}

function JobPagination({ result, changePage }: { result: PublicJobSearch; changePage: (page: number) => void }) {
  if (result.total_pages <= 1) return null;
  return (
    <nav className="job-pagination" aria-label="Jobs pagination">
      <button className="secondary" disabled={result.page <= 1} onClick={() => changePage(result.page - 1)}>
        Previous page
      </button>
      <p className="muted">Page {result.page} of {result.total_pages} · {result.total} jobs</p>
      <button className="secondary" disabled={result.page >= result.total_pages} onClick={() => changePage(result.page + 1)}>
        Next page
      </button>
    </nav>
  );
}

export type JobsContentProps = {
  result: PublicJobSearch | null;
  error: string;
  search: JobDiscoverySearch;
  selected: string | null;
  detail: PublicJobDetail | null;
  detailError: JobDetailError | null;
  pendingJobIds: Set<string>;
  selectJob: (jobId: string) => void;
  changePage: (page: number) => void;
  clearFilters: () => void;
  browseJobs?: () => void;
  retryJobs: () => void;
  retryDetail: () => void;
  toggleSave: (job: PublicJob | PublicJobDetail) => void;
  toggleHide: (job: PublicJob | PublicJobDetail) => void;
  trackedJobIds?: Set<string>;
  onTracked?: (application: Application) => void;
};

export function JobsContent({
  result,
  error,
  search,
  selected,
  detail,
  detailError,
  pendingJobIds,
  selectJob,
  changePage,
  clearFilters,
  browseJobs,
  retryJobs,
  retryDetail,
  toggleSave,
  toggleHide,
  trackedJobIds = new Set<string>(),
  onTracked,
}: JobsContentProps) {
  if (result === null) {
    return error ? (
      <section className="auth-card dashboard-card">
        <p role="alert" className="auth-error">Could not load jobs. {error}</p>
        <button className="secondary" onClick={retryJobs}>Retry jobs</button>
      </section>
    ) : <div className="jobs-loading" role="status"><p>Loading jobs…</p>{[1, 2, 3].map((key) => <Skeleton key={key} className="job-result-skeleton" />)}</div>;
  }
  if (!result.items.length) {
    const filtered = hasFilters(search);
    const title = filtered ? "No jobs match these filters" : search.view === "saved" ? "No saved jobs yet" : search.view === "hidden" ? "No hidden jobs" : "No jobs available right now";
    const message = filtered ? "Try removing a filter to broaden your search." : search.view === "saved" ? "Save jobs you’re interested in so you can return to them here." : search.view === "hidden" ? "Jobs you hide will appear here." : "New opportunities will appear here when they become available.";
    return <section className="jobs-empty"><span className="jobs-empty-icon" aria-hidden="true"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="7" width="18" height="14" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18M10 12v3h4v-3"/></svg></span><h2>{title}</h2><p className="muted">{message}</p>
      {filtered ? <button className="secondary" onClick={clearFilters}>Clear filters</button> : search.view === "saved" && browseJobs ? <button className="secondary" onClick={browseJobs}>Browse jobs</button> : null}
    </section>;
  }

  const selectedDetail = detail?.id === selected ? detail : null;
  const selectedDetailError = detailError?.jobId === selected ? detailError.message : "";
  return (
    <div className="jobs-layout">
      <section className="jobs-results-pane" aria-label="Job results" tabIndex={0}>
        <h2>{search.view === "all" ? "Newest matching jobs" : displayChoice(search.view) + " jobs"}</h2>
        <ul className="jobs-list">
          {result.items.map((job) => (
            <li key={job.id}>
              <article className="job-card" data-selected={selected === job.id}>
                <button className="job-result-select" type="button" aria-pressed={selected === job.id} onClick={() => selectJob(job.id)}><strong>{job.title}</strong><span className="job-result-company">{job.company_name}</span><span className="job-result-meta">{[job.work_mode ? displayChoice(job.work_mode) : null, job.employment_type ? displayChoice(job.employment_type) : null].filter(Boolean).join(" · ")}</span></button>
                <JobFreshness job={job} />
                <div className="job-actions"><button className="secondary" type="button" disabled={pendingJobIds.has(job.id)} onClick={() => toggleSave(job)}>{job.saved ? "Unsave" : "Save"}</button><button className="secondary" type="button" disabled={pendingJobIds.has(job.id)} onClick={() => toggleHide(job)}>{job.hidden ? "Unhide" : "Hide"}</button></div>
              </article>
            </li>
          ))}
        </ul>
        <JobPagination result={result} changePage={changePage} />
      </section>
      {selected && !selectedDetail ? (
        selectedDetailError ? <JobDetailFailure message={selectedDetailError} retry={retryDetail} /> : <section className="auth-card dashboard-card" role="status"><p>Loading job details…</p><Skeleton className="job-result-skeleton" /><Skeleton className="job-result-skeleton" /></section>
      ) : (
        <JobDetail
          job={selectedDetail}
          onSave={selectedDetail ? () => toggleSave(selectedDetail) : undefined}
          onHide={selectedDetail ? () => toggleHide(selectedDetail) : undefined}
          pending={selectedDetail ? pendingJobIds.has(selectedDetail.id) : false}
          tracked={selectedDetail ? trackedJobIds.has(selectedDetail.id) : false}
          onTracked={onTracked}
        />
      )}
    </div>
  );
}

export function JobsPage() {
  const { user, error: sessionError, refresh } = useAuth();
  const [search, setSearch] = useState<JobDiscoverySearch>(browserSearch);
  const [draft, setDraft] = useState<JobDiscoveryDraft>(() => toDraft(browserSearch()));
  const [result, setResult] = useState<PublicJobSearch | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PublicJobDetail | null>(null);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState<JobDetailError | null>(null);
  const [actionError, setActionError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [detailAttempt, setDetailAttempt] = useState(0);
  const [roles, setRoles] = useState<CatalogItem[]>([]);
  const [locations, setLocations] = useState<CatalogLocation[]>([]);
  const [filterError, setFilterError] = useState("");
  const [savedSearches, setSavedSearches] = useState<SavedJobSearch[] | null>(null);
  const [savedError, setSavedError] = useState("");
  const [savedAttempt, setSavedAttempt] = useState(0);
  const [savedName, setSavedName] = useState("");
  const savedDialog = useRef<HTMLDialogElement>(null);
  const savedTrigger = useRef<HTMLButtonElement>(null);
  const [pendingJobIds, setPendingJobIds] = useState<Set<string>>(() => new Set());
  const [trackedJobIds, setTrackedJobIds] = useState<Set<string>>(() => new Set());

  function fail(reason: unknown) {
    setError(authErrorMessage(reason));
    if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
  }

  function resetSelection() {
    setSelected(null);
    setDetail(null);
    setDetailError(null);
  }

  function navigateSearch(next: JobDiscoverySearch) {
    if (typeof window !== "undefined") {
      const query = serializeJobDiscoverySearch(next);
      const target = window.location.pathname + (query ? "?" + query : "");
      if (window.location.pathname + window.location.search !== target) {
        window.history.pushState(null, "", target);
      }
    }
    resetSelection();
    setSearch(next);
    setDraft(toDraft(next));
  }

  function selectJob(jobId: string) {
    setDetail(null);
    setDetailError(null);
    setSelected(jobId);
    setDetailAttempt((value) => value + 1);
  }

  function retryDetail() {
    setDetail(null);
    setDetailError(null);
    setDetailAttempt((value) => value + 1);
  }

  function commitSearch(nextDraft: JobDiscoveryDraft, page = 1) {
    navigateSearch({ ...nextDraft, view: search.view, page });
  }

  function clearFilters() {
    navigateSearch({ ...DEFAULT_SEARCH, view: search.view });
  }

  function applyUserState(state: JobUserState) {
    setResult((current) => current === null ? null : {
      ...current,
      items: current.items.map((job) => job.id === state.job_id ? { ...job, ...state } : job),
    });
    setDetail((current) => current?.id === state.job_id ? { ...current, ...state } : current);
  }

  async function changeJobState(job: PublicJob | PublicJobDetail, change: JobUserStateUpdate) {
    setActionError("");
    setPendingJobIds((current) => new Set(current).add(job.id));
    try {
      const state = await apiClient.updateJobState(job.id, change);
      applyUserState(state);
      const removesFromView = (change.hidden === true && search.view !== "hidden")
        || (change.hidden === false && search.view === "hidden");
      if (removesFromView) {
        setResult((current) => current === null ? null : {
          ...current,
          total: Math.max(0, current.total - 1),
          items: current.items.filter((item) => item.id !== job.id),
        });
        if (selected === job.id) resetSelection();
        setAttempt((value) => value + 1);
      }
    } catch (reason) {
      setActionError(authErrorMessage(reason));
      if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
    } finally {
      setPendingJobIds((current) => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  }

  async function saveCurrentSearch() {
    setSavedError("");
    const name = savedName.trim();
    if (!name) {
      setSavedError("Enter a concise name before saving this search.");
      return;
    }
    try {
      const saved = await apiClient.createSavedSearch({
        name,
        criteria: toSavedSearchCriteria(search),
        alert_mode: "OFF",
      });
      setSavedSearches((current) => current === null ? [saved] : [saved, ...current]);
      setSavedName("");
    } catch (reason) {
      setSavedError(authErrorMessage(reason));
      if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
    }
  }

  async function updateSavedCriteria(saved: SavedJobSearch) {
    setSavedError("");
    try {
      const updated = await apiClient.updateSavedSearch(saved.id, { criteria: toSavedSearchCriteria(search) });
      setSavedSearches((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? current);
    } catch (reason) {
      setSavedError(authErrorMessage(reason));
    }
  }

  async function updateSavedAlertMode(saved: SavedJobSearch, alert_mode: SavedSearchAlertMode) {
    setSavedError("");
    try {
      const updated = await apiClient.updateSavedSearch(saved.id, { alert_mode });
      setSavedSearches((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? current);
    } catch (reason) {
      setSavedError(authErrorMessage(reason));
      if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
    }
  }

  async function renameSavedSearch(saved: SavedJobSearch) {
    if (typeof window === "undefined") return;
    const name = window.prompt("Saved search name", saved.name);
    if (name === null || !name.trim()) return;
    setSavedError("");
    try {
      const updated = await apiClient.updateSavedSearch(saved.id, { name: name.trim() });
      setSavedSearches((current) => current?.map((item) => item.id === updated.id ? updated : item) ?? current);
    } catch (reason) {
      setSavedError(authErrorMessage(reason));
    }
  }

  async function deleteSavedSearch(saved: SavedJobSearch) {
    if (typeof window !== "undefined" && !window.confirm("Delete saved search " + saved.name + "?")) return;
    setSavedError("");
    try {
      await apiClient.deleteSavedSearch(saved.id);
      setSavedSearches((current) => current?.filter((item) => item.id !== saved.id) ?? current);
    } catch (reason) {
      setSavedError(authErrorMessage(reason));
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const onPopState = () => {
      const next = readJobDiscoverySearch(window.location.search);
      setSearch(next);
      setDraft(toDraft(next));
      setSelected(null);
      setDetail(null);
      setDetailError(null);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    setFilterError("");
    Promise.all([apiClient.listRoles(), apiClient.listLocations()])
      .then(([nextRoles, nextLocations]) => {
        if (!active) return;
        setRoles(nextRoles);
        setLocations(nextLocations);
      })
      .catch((reason) => {
        if (active) setFilterError(authErrorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [user]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    setSavedSearches(null);
    setSavedError("");
    apiClient.listSavedSearches()
      .then((items) => {
        if (active) setSavedSearches(items);
      })
      .catch((reason) => {
        if (active) setSavedError(authErrorMessage(reason));
      });
    return () => {
      active = false;
    };
  }, [savedAttempt, user]);

  useEffect(() => {
    if (!user) return;
    let active = true;
    setResult(null);
    setError("");
    apiClient.listJobs(toJobSearchParams(search))
      .then((data) => {
        if (!active) return;
        setResult(data);
        setSelected((current) => current && data.items.some((job) => job.id === current) ? current : null);
      })
      .catch((reason) => {
        if (active) fail(reason);
      });
    return () => {
      active = false;
    };
  }, [attempt, refresh, search, user]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      setDetailError(null);
      return;
    }
    let active = true;
    setDetail(null);
    setDetailError(null);
    apiClient.getJob(selected)
      .then((data) => {
        if (!active) return;
        setDetail(data);
        if (!data.unseen) return;
        apiClient.updateJobState(data.id, { viewed: true })
          .then((state) => {
            if (!active) return;
            setResult((current) => current === null ? null : {
              ...current,
              items: current.items.map((job) => job.id === state.job_id ? { ...job, ...state } : job),
            });
            setDetail((current) => current?.id === state.job_id ? { ...current, ...state } : current);
          })
          .catch((reason) => {
            if (active) setActionError(authErrorMessage(reason));
          });
      })
      .catch((reason) => {
        if (!active) return;
        setDetailError({ jobId: selected, message: authErrorMessage(reason) });
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => {
      active = false;
    };
  }, [detailAttempt, refresh, selected]);

  return (
    <main className="auth-shell dashboard-shell jobs-shell">
      <header className="jobs-heading"><div><h1 className="profile-title">Jobs</h1><p className="muted">Discover opportunities that fit your goals.</p></div>
      {user ? <button ref={savedTrigger} className="secondary" type="button" onClick={() => savedDialog.current?.showModal()}>Saved searches</button> : null}</header>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to browse jobs.</p>
            : (
              <>
                {filterError ? <p role="alert" className="auth-error">Could not load filter choices. {filterError}</p> : null}
                <JobSearchControls
                  draft={draft}
                  roles={roles}
                  locations={locations}
                  onChange={setDraft}
                  onSubmit={() => commitSearch(draft)}
                  onClear={clearFilters}
                />
                <AppliedFilters search={search} roles={roles} onChange={navigateSearch} onClear={clearFilters} />
                <div className="jobs-results-bar"><FeedViewTabs view={search.view} onChange={(view) => navigateSearch({ ...search, view, page: 1 })} />{result ? <p className="muted">{result.total} {result.total === 1 ? "job" : "jobs"}{hasFilters(search) ? " matching your filters" : ""}</p> : null}</div>
                <dialog ref={savedDialog} className="jobs-saved-dialog" aria-label="Saved searches" onClose={() => savedTrigger.current?.focus()} onClick={(event) => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) savedDialog.current?.close(); } }}>
                <button type="button" className="secondary jobs-dialog-close" onClick={() => savedDialog.current?.close()}>Close saved searches</button>
                <SavedSearchControls
                  searches={savedSearches}
                  name={savedName}
                  error={savedError}
                  onNameChange={setSavedName}
                  onCreate={() => void saveCurrentSearch()}
                  onOpen={(saved) => { navigateSearch(fromSavedSearchCriteria(saved.criteria)); savedDialog.current?.close(); }}
                  onUpdateCriteria={(saved) => void updateSavedCriteria(saved)}
                  onRename={(saved) => void renameSavedSearch(saved)}
                  onDelete={(saved) => void deleteSavedSearch(saved)}
                  onAlertModeChange={(saved, mode) => void updateSavedAlertMode(saved, mode)}
                  onRetry={() => setSavedAttempt((value) => value + 1)}
                />
                </dialog>
                {actionError ? <p role="alert" className="auth-error">{actionError}</p> : null}
                <JobsContent
                  result={result}
                  error={error}
                  search={search}
                  selected={selected}
                  detail={detail}
                  detailError={detailError}
                  pendingJobIds={pendingJobIds}
                  selectJob={selectJob}
                  changePage={(page) => navigateSearch({ ...search, page })}
                  clearFilters={clearFilters}
                  browseJobs={() => navigateSearch({ ...DEFAULT_SEARCH, view: "all" })}
                  retryJobs={() => setAttempt((value) => value + 1)}
                  retryDetail={retryDetail}
                  toggleSave={(job) => void changeJobState(job, { saved: !job.saved })}
                  toggleHide={(job) => void changeJobState(job, { hidden: !job.hidden })}
                  trackedJobIds={trackedJobIds}
                  onTracked={(application) => setTrackedJobIds((current) => new Set(current).add(application.canonical_job_id))}
                />
              </>
            )}
    </main>
  );
}
