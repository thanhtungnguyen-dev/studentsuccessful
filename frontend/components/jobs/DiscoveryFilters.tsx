"use client";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { CatalogItem, CatalogLocation } from "../../lib/api/client";
import type { JobDiscoveryDraft, JobDiscoverySearch } from "./JobsPage";
export const EMPLOYMENT_TYPES = ["INTERNSHIP", "CO_OP", "FULL_TIME", "PART_TIME", "CONTRACT", "NEW_GRAD"];
export const WORK_MODES = ["REMOTE", "HYBRID", "ON_SITE"];
export const RECENCY_OPTIONS = [{ value: "1h", label: "Last hour" }, { value: "24h", label: "Last 24 hours" }, { value: "3d", label: "Last 3 days" }, { value: "7d", label: "Last 7 days" }, { value: "all", label: "All active jobs" }] as const;
const labelOf = (s: string) => s.toLowerCase().replaceAll("_", " ").replace(/^./, (s) => s.toUpperCase());
type MultiField = "roles" | "countries" | "regions" | "cities" | "job_types" | "work_modes";
const fields: MultiField[] = ["roles", "countries", "regions", "cities", "job_types", "work_modes"];
export function JobFilterPopover({ label, count = 0, children }: { label: string; count?: number; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return <div className="job-filter-popover" ref={root} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }} onKeyDown={(e) => {
    if (e.key === "Escape" && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); trigger.current?.focus(); }
  }}>
    <button ref={trigger} type="button" className="secondary job-filter-trigger" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>{label}{count > 0 ? <span className="job-filter-count">{count}</span> : null}<span aria-hidden="true">⌄</span></button>
    <div id={id} className="job-filter-panel" hidden={!open} role="group" aria-label={label}>{children}<button type="button" className="secondary job-filter-done" onClick={() => { setOpen(false); trigger.current?.focus(); }}>Done</button></div>
  </div>;
}
export function DiscoveryFilters({ draft, roles, locations, onChange, onSubmit, onClear }: {
  draft: JobDiscoveryDraft; roles: CatalogItem[]; locations: CatalogLocation[];
  onChange: (next: JobDiscoveryDraft) => void; onSubmit: () => void; onClear: () => void;
}) {
  const countries = [...new Set(locations.map((x) => x.country_code))].sort();
  const regions = [...new Set(locations.map((x) => x.state_province).filter((x): x is string => Boolean(x)))].sort();
  const cities = [...new Set(locations.map((x) => x.city))].sort();
  function choices(field: MultiField, options: { value: string; label: string }[], empty: string) {
    return options.length ? <div className="job-filter-options">{options.map(({ value, label }) => <label key={value}><input type="checkbox" checked={draft[field].includes(value)} onChange={(e) => onChange({ ...draft, [field]: e.target.checked ? [...draft[field], value] : draft[field].filter((x) => x !== value) })} />{label}</label>)}</div> : <p className="muted">{empty}</p>;
  }
  const options = (values: readonly string[], pretty = false) => values.map((value) => ({ value, label: pretty ? labelOf(value) : value }));
  return <form className="job-discovery-controls" aria-label="Job filters" onSubmit={(e) => { e.preventDefault(); onSubmit(); }}>
    <label className="job-keyword">Keywords<input type="search" value={draft.keyword} onChange={(e) => onChange({ ...draft, keyword: e.target.value })} placeholder="Search job titles, companies, descriptions…" /></label>
    <div className="job-filter-toolbar">
      <JobFilterPopover label="Role" count={draft.roles.length}>{choices("roles", roles.filter((r) => Boolean(r.slug)).map((r) => ({ value: r.slug!, label: r.name })), "No roles available for the current jobs.")}</JobFilterPopover>
      <JobFilterPopover label="Location" count={draft.countries.length}>{choices("countries", options(countries), "No locations available for the current jobs.")}</JobFilterPopover>
      <JobFilterPopover label="Job type" count={draft.job_types.length}>{choices("job_types", options(EMPLOYMENT_TYPES, true), "No job types available.")}</JobFilterPopover>
      <JobFilterPopover label="Work mode" count={draft.work_modes.length}>{choices("work_modes", options(WORK_MODES, true), "No work modes available.")}</JobFilterPopover>
      <JobFilterPopover label="Recency" count={draft.recency === "all" ? 0 : 1}><div className="job-filter-options">{RECENCY_OPTIONS.map((o) => <label key={o.value}><input type="radio" name="job-recency" checked={draft.recency === o.value} onChange={() => onChange({ ...draft, recency: o.value })} />{o.label}</label>)}</div></JobFilterPopover>
      <JobFilterPopover label="More filters" count={draft.regions.length + draft.cities.length + Number(Boolean(draft.company)) + Number(Boolean(draft.requirement))}>
        <fieldset><legend>Region or province</legend>{choices("regions", options(regions), "No regions available.")}</fieldset><fieldset><legend>City</legend>{choices("cities", options(cities), "No cities available.")}</fieldset>
        <label>Company<input value={draft.company} onChange={(e) => onChange({ ...draft, company: e.target.value })} /></label><label>Skill or technology<input value={draft.requirement} onChange={(e) => onChange({ ...draft, requirement: e.target.value })} /></label>
      </JobFilterPopover>
      <div className="job-filter-actions"><button type="submit">Apply filters</button><button className="secondary" type="button" onClick={onClear}>Clear filters</button></div>
    </div><p className="job-filter-help muted">Choose your filters, then select Apply filters.</p>
  </form>;
}
export function AppliedFilters({ search, roles, onChange, onClear }: { search: JobDiscoverySearch; roles: CatalogItem[]; onChange: (search: JobDiscoverySearch) => void; onClear: () => void }) {
  const chips = fields.flatMap((field) => search[field].map((value) => ({ key: field + value, label: field === "roles" ? roles.find((r) => r.slug === value)?.name || value : field === "job_types" || field === "work_modes" ? labelOf(value) : value, next: { ...search, [field]: search[field].filter((x) => x !== value), page: 1 } })));
  for (const field of ["keyword", "company", "requirement", "recency"] as const) {
    if (field === "recency" ? search.recency === "all" : !search[field].trim()) continue;
    chips.push({ key: field, label: field === "recency" ? RECENCY_OPTIONS.find((o) => o.value === search.recency)!.label : search[field], next: { ...search, [field]: field === "recency" ? "all" : "", page: 1 } });
  }
  if (!chips.length) return null;
  return <div className="job-applied-filters" aria-label="Applied filters"><span>Applied:</span>{chips.map((c) => <button className="secondary" type="button" key={c.key} aria-label={"Remove " + c.label + " filter"} onClick={() => onChange(c.next)}>{c.label}<span aria-hidden="true">×</span></button>)}<button className="secondary" type="button" onClick={onClear}>Clear all</button></div>;
}
