"use client";
import Link from "next/link";
import { ReturnToReview } from "../onboarding/ReturnToReview";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, ApiError, authErrorMessage, type Preferences } from "../../lib/api/client";
import { GROUPS, WORK_MODES, EMPLOYMENT_TYPES, completePreferences, toggleSelection, addCustom } from "../../lib/preferences/form";
import { useAuth } from "../auth/AuthProvider";

type Options = Record<typeof GROUPS[number]["key"], Array<{ id: string; name: string }>>;
export function PreferencesPage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell preferences-shell"><Link href="/" className="brand">StudentSuccessful</Link><ReturnToReview /><h1 className="profile-title">Career Preferences</h1>
    <p className="muted">Choose what you want. Technology interests are preferences, not claims about your skills.</p>
    {user === undefined ? error ? <><p role="alert">{error}</p><button onClick={() => void refresh().catch(() => {})}>Retry</button></> : <p role="status">Checking your session…</p>
      : user === null ? <p>Please <Link href="/login">Login</Link> to view preferences.</p> : <PreferencesForm key={user.id} />}
  </main>;
}
function PreferencesForm() {
  const { refresh } = useAuth();
  const [values, setValues] = useState<Required<Preferences> | null>(null);
  const [options, setOptions] = useState<Options | null>(null);
  const [custom, setCustom] = useState<Record<string, string>>({});
  const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false); const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true; setError("");
    Promise.all([apiClient.getPreferences(), apiClient.listRoles(), apiClient.listIndustries(), apiClient.listLocations(), apiClient.listCompanies(), apiClient.listSkills()])
      .then(([saved, roles, industries, locations, companies, skills]) => {
        if (!active) return;
        setValues(completePreferences(saved)); setOptions({ role_ids: roles, industry_ids: industries, location_ids: locations.map(row => ({ id: row.id, name: [row.city, row.state_province, row.country_code].filter(Boolean).join(", ") })), company_ids: companies, skill_ids: skills });
      }).catch(error => { if (active) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); } });
    return () => { active = false; };
  }, [attempt, refresh]);
  async function save(event: FormEvent) {
    event.preventDefault(); if (!values || busy) return; setBusy(true);setError("");setSuccess("");
    try { setValues(completePreferences(await apiClient.replacePreferences(completePreferences(values)))); setSuccess("Preferences saved."); }
    catch(error) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    finally { setBusy(false); }
  }
  if (!values || !options) return error ? <><p role="alert" className="auth-error">{error}</p><button className="secondary" onClick={() => setAttempt(x => x + 1)}>Retry loading</button></> : <p role="status">Loading preferences and catalogs…</p>;
  return <form className="preferences-form" onSubmit={save} aria-busy={busy}>
    <fieldset disabled={busy}>
      {GROUPS.map(group => <section className="auth-card preference-group" key={group.key}>
        <h2>{group.label}</h2>
        {!options[group.key].length && <p className="muted">No catalog choices available. You can add an explicit Other value.</p>}
        <div className="preference-options">{options[group.key].map(option => <label key={option.id}><input type="checkbox" checked={values[group.key].includes(option.id)} onChange={() => { setValues({ ...values, [group.key]: toggleSelection(values[group.key], option.id) }); setSuccess(""); }} />{option.name}</label>)}</div>
        {values[group.key].filter(id => !options[group.key].some(option => option.id === id)).map(id => <div key={id} className="preference-custom">Saved choice unavailable in this catalog: {id}<button className="secondary" type="button" onClick={() => setValues({ ...values, [group.key]: values[group.key].filter(x => x !== id) })}>Remove saved choice</button></div>)}
        <label htmlFor={`other-${group.type}`}>Other {group.label.toLowerCase()}</label>
        <div className="auth-actions"><input id={`other-${group.type}`} value={custom[group.type] ?? ""} maxLength={150} onChange={event => setCustom({ ...custom, [group.type]: event.target.value })} /><button className="secondary" type="button" onClick={() => {
          try { setValues(addCustom(values, group.type, custom[group.type] ?? "")); setCustom({ ...custom, [group.type]: "" }); setError(""); setSuccess(""); }
          catch(error) { setError(error instanceof Error ? error.message : "Check custom value."); }
        }}>Add other {group.label.toLowerCase()}</button></div>
        {values.custom_values.map((item, index) => item.preference_type === group.type && <div className="preference-custom" key={index}><span>{item.value} (custom)</span><button className="secondary" type="button" aria-label={`Remove custom ${item.value}`} onClick={() => setValues({ ...values, custom_values: values.custom_values.filter((_, i) => i !== index) })}>Remove</button></div>)}
      </section>)}
      <section className="auth-card preference-group"><h2>Work modes</h2><div className="preference-options">{WORK_MODES.map(mode => <label key={mode}><input type="checkbox" checked={values.work_modes.includes(mode)} onChange={() => setValues({ ...values, work_modes: toggleSelection(values.work_modes, mode) })} />{mode.replaceAll("_", " ")}</label>)}</div></section>
      <section className="auth-card preference-group"><h2>Employment types</h2><div className="preference-options">{EMPLOYMENT_TYPES.map(type => <label key={type}><input type="checkbox" checked={values.employment_types.includes(type)} onChange={() => setValues({ ...values, employment_types: toggleSelection(values.employment_types, type) })} />{type.replaceAll("_", " ")}</label>)}</div></section>
    </fieldset>
    <p className="muted">Saving replaces all saved preferences with the selections shown above.</p>
    {error && <p className="auth-error" role="alert">{error}</p>}{success && <p className="profile-success" role="status">{success}</p>}
    <button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save preferences"}</button>
  </form>;
}
