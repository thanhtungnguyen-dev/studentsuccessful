import React, { type ReactNode } from "react";
import Link from "next/link";
import { type ReviewData, REVIEW_SECTIONS } from "../../lib/onboarding/review";
import { profileSections } from "../../lib/profile/form";
import { completePreferences, GROUPS } from "../../lib/preferences/form";
import { STATUS_LABELS } from "../../lib/work-authorization/form";

function Field({ label, value }: { label: string; value: unknown }) {
  const display = value === null || value === undefined || value === "" ? "Not provided" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value);
  return <div><dt>{label}</dt><dd>{display}</dd></div>;
}
function Section({ index, children }: { index: number; children: ReactNode }) {
  const section = REVIEW_SECTIONS[index];
  return <section className="auth-card review-section" aria-labelledby={`review-${section.key}`}>
    <header><h2 id={`review-${section.key}`}>{section.title}</h2><Link className="secondary" href={section.href}>Edit {section.title}</Link></header>{children}
  </section>;
}
export function ReviewSections({ data }: { data: ReviewData }) {
  const preferences = completePreferences(data.preferences);
  return <div className="review-sections">
    <Section index={0}>{data.profile ? <dl>{profileSections.flatMap(section => section.fields).map(field => <Field key={field.key} label={field.label} value={data.profile?.[field.key]} />)}</dl> : <p className="muted">No profile saved yet.</p>}</Section>
    <Section index={1}>{data.education.length ? data.education.map(row => <article key={row.id}><h3>{row.institution_name}</h3><dl>
      <Field label="Degree level" value={row.degree_level} /><Field label="Major" value={row.major} /><Field label="Minor" value={row.minor} /><Field label="Study year" value={row.study_year} />
      <Field label="Start date" value={row.start_date} /><Field label="Expected graduation" value={`${row.expected_grad_year}-${String(row.expected_grad_month).padStart(2, "0")}`} />
      <Field label="GPA / scale" value={row.gpa_value == null ? null : `${row.gpa_value} / ${row.gpa_scale}`} /><Field label="Include GPA on applications" value={row.gpa_include_on_apps ?? false} /><Field label="Primary education" value={row.is_primary ?? false} />
    </dl></article>) : <p className="muted">No education records saved.</p>}</Section>
    <Section index={2}>{data.employment.length ? data.employment.map(row => <article key={row.id}><h3>{row.employer_name}</h3><dl>
      <Field label="Job title" value={row.job_title} /><Field label="Employment location" value={row.location} /><Field label="Start date" value={row.start_date} /><Field label="End date" value={row.end_date} /><Field label="Currently employed" value={row.currently_employed ?? false} /><Field label="Description" value={row.description} />
    </dl></article>) : <p className="muted">No employment records saved.</p>}</Section>
    <Section index={3}>{data.authorization.length ? data.authorization.map(row => <article key={row.id}><h3>{row.country_code}</h3><dl>
      <Field label="Authorization status" value={STATUS_LABELS[row.authorization_status]} /><Field label="Current sponsorship required" value={row.requires_current_sponsorship ?? false} /><Field label="Future sponsorship required" value={row.requires_future_sponsorship ?? false} /><Field label="Notes" value={row.notes} /><Field label="Last confirmed (UTC)" value={row.last_confirmed_at} />
    </dl></article>) : <p className="muted">No work authorization records saved.</p>}</Section>
    <Section index={4}><p className="muted">Desired choices only. Technology interests are not skill claims.</p>
      {GROUPS.map(group => <div key={group.key} className="review-preference"><h3>{group.label}</h3>
        {!preferences[group.key].length && !preferences.custom_values.some(item => item.preference_type === group.type) && <p className="muted">No selections saved.</p>}
        <ul>{preferences[group.key].map(id => <li key={id}>{data.catalogs[group.key].find(item => item.id === id)?.name ?? `Saved catalog selection (label unavailable): ${id}`}</li>)}
          {preferences.custom_values.filter(item => item.preference_type === group.type).map((item, i) => <li className="review-custom" key={`custom-${i}`}>{item.value} <span className="muted">(custom)</span></li>)}
        </ul>
      </div>)}
      <dl><Field label="Work modes" value={preferences.work_modes.map(x => x.replaceAll("_", " ")).join(", ")} /><Field label="Employment types" value={preferences.employment_types.map(x => x.replaceAll("_", " ")).join(", ")} /></dl>
    </Section>
  </div>;
}
