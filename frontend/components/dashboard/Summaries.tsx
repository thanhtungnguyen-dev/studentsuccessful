import Link from "next/link";
import type { Profile, Education, Employment, WorkAuthorization } from "../../lib/api/client";
import type { DashboardPreferences } from "../../lib/dashboard/data";
import { profileSections } from "../../lib/profile/form";
import { completePreferences, GROUPS } from "../../lib/preferences/form";
import { STATUS_LABELS } from "../../lib/work-authorization/form";

function Fact({label, value}: {label: string; value: unknown}) {
  return <div><dt>{label}</dt><dd>{value === null || value === undefined || value === "" ? "Not provided" : typeof value === "boolean" ? value ? "Yes" : "No" : String(value)}</dd></div>;
}
export function ProfileSummary({data}: {data: Profile | null}) {
  if (!data) return <div className="empty-summary"><h3>Your personal information</h3><p>No profile saved yet. Keep your application details in one place.</p><Link className="action-link" href="/profile">Add Personal Information</Link></div>;
  const keys = ["legal_first_name", "legal_last_name", "preferred_name", "phone_number", "address_city", "address_country_code"];
  return <dl>{profileSections.flatMap(group => group.fields).filter(field => keys.includes(field.key)).map(field => <Fact key={field.key} label={field.label} value={data[field.key]} />)}</dl>;
}
export function EducationSummary({data}: {data: Education[]}) {
  if (!data.length) return <div className="empty-summary"><h3>Add your education</h3><p>No education records saved. Show where and what you are studying.</p><Link className="action-link" href="/education">Add Education</Link></div>;
  return <>{data.map(row => <article key={row.id}><h3>{row.institution_name}</h3><dl>
    <Fact label="Degree level" value={row.degree_level} /><Fact label="Major" value={row.major} />
    <Fact label="Expected graduation" value={`${row.expected_grad_year}-${String(row.expected_grad_month).padStart(2,"0")}`} />
    <Fact label="Primary education" value={row.is_primary ?? false} />
  </dl></article>)}</>;
}
export function EmploymentSummary({data}: {data: Employment[]}) {
  if (!data.length) return <div className="empty-summary"><h3>Add your experience</h3><p>No employment records saved. Keep your work history ready for your next application.</p><Link className="action-link" href="/employment">Add Employment</Link></div>;
  return <>{data.map(row => <article key={row.id}><h3>{row.employer_name}</h3><dl>
    <Fact label="Job title" value={row.job_title} /><Fact label="Employment location" value={row.location} />
    <Fact label="Start date" value={row.start_date} /><Fact label="End date" value={row.end_date} />
    <Fact label="Currently employed" value={row.currently_employed ?? false} />
  </dl></article>)}</>;
}
export function AuthorizationSummary({data}: {data: WorkAuthorization[]}) {
  if (!data.length) return <div className="empty-summary"><h3>Clarify your work eligibility</h3><p>No work authorization records saved. Save your authorization and sponsorship details.</p><Link className="action-link" href="/work-authorization">Add Work Authorization</Link></div>;
  return <>{data.map(row => <article key={row.id}><h3>{row.country_code}</h3><dl>
    <Fact label="Authorization status" value={STATUS_LABELS[row.authorization_status]} />
    <Fact label="Current sponsorship required" value={row.requires_current_sponsorship} /><Fact label="Future sponsorship required" value={row.requires_future_sponsorship} />
  </dl></article>)}</>;
}
export function PreferencesSummary({data, compact = false}: {data: DashboardPreferences; compact?: boolean}) {
  const preferences=completePreferences(data.preferences);
  return <><p className="muted">Desired choices only. Technology interests are not skill claims.</p>
    <div className="dashboard-preferences">{GROUPS.filter(group => !compact || preferences[group.key].length || preferences.custom_values.some(item => item.preference_type === group.type)).map(group => <div key={group.key}><h3>{group.label}</h3>
      {!preferences[group.key].length && !preferences.custom_values.some(item => item.preference_type === group.type) ? <p className="muted">No selections saved.</p> : <ul>
        {preferences[group.key].map(id => <li key={id}>{data.catalogs[group.key].find(item => item.id === id)?.name ?? `Saved catalog selection (label unavailable): ${id}`}</li>)}
        {preferences.custom_values.filter(item => item.preference_type === group.type).map((item,index) => <li className="review-custom" key={`custom-${index}`}>{item.value} <span className="muted">(custom)</span></li>)}
      </ul>}
    </div>)}</div>
    <dl><Fact label="Work modes" value={preferences.work_modes.map(x => x.replaceAll("_", " ")).join(", ")} /><Fact label="Employment types" value={preferences.employment_types.map(x => x.replaceAll("_", " ")).join(", ")} /></dl>
  </>;
}
