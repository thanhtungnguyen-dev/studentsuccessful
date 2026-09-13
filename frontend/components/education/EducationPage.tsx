"use client";

import Link from "next/link";
import { ReturnToReview } from "../onboarding/ReturnToReview";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, ApiError, authErrorMessage, type Education } from "../../lib/api/client";
import { changedEducationFields, degreeLevels, educationFormValues, educationPayload, months, studyYears } from "../../lib/education/form";
import { useAuth } from "../auth/AuthProvider";

export function EducationPage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell education-shell">
    <Link href="/" className="brand">StudentSuccessful</Link><ReturnToReview />
    <h1 className="profile-title">Education</h1>
    <p className="muted">Your academic facts, entered by you. GPA stays on its original scale.</p>
    {user === undefined ? (error ? <div><p role="alert">{error}</p><button className="primary" onClick={() => { void refresh().catch(() => {}); }}>Try again</button></div> : <p role="status">Checking your session…</p>)
      : user === null ? <p className="auth-footer">Please <Link href="/login">Login</Link> to view education.</p>
      : <EducationContent key={user.id} />}
  </main>;
}

function EducationContent() {
  const { refresh } = useAuth();
  const [records, setRecords] = useState<Education[] | null>(null);
  const [editor, setEditor] = useState<Education | "new" | null>(null);
  const [deleting, setDeleting] = useState<Education | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    apiClient.listEducation().then((items) => { if (active) setRecords(items); }).catch((error) => {
      if (active) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    });
    return () => { active = false; };
  }, [attempt, refresh]);

  async function remove() {
    if (!deleting || busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await apiClient.deleteEducation(deleting.id);
      setRecords((current) => current?.filter((record) => record.id !== deleting.id) ?? null);
      setDeleting(null); setSuccess("Education deleted.");
    } catch (error) {
      setError(authErrorMessage(error));
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    } finally { setBusy(false); }
  }

  function saved(record: Education) {
    setRecords((current) => {
      const items = (current ?? []).map((item) => item.id === record.id ? record : record.is_primary ? { ...item, is_primary: false } : item);
      return items.some((item) => item.id === record.id) ? items : [...items, record];
    });
    setEditor(null); setError(""); setSuccess("Education saved.");
  }

  return <>
    {error && <div><p className="auth-error" role="alert">{error}</p><button className="secondary" onClick={() => { setEditor(null); setDeleting(null); setAttempt((value) => value + 1); }}>Reload list</button></div>}
    {success && <p className="profile-success" role="status">{success}</p>}
    {records === null && !error && <p role="status">Loading education…</p>}
    {records !== null && <>
      {editor ? <EducationForm key={editor === "new" ? "new" : editor.id} record={editor === "new" ? undefined : editor} onSave={saved} onCancel={() => setEditor(null)} />
        : <button className="primary education-add" disabled={busy || deleting !== null} onClick={() => { setEditor("new"); setSuccess(""); }}>Add education</button>}
      {!records.length && <p className="muted">No education records yet.</p>}
      <div className="education-list">{records.map((record) => <article className="auth-card education-record" key={record.id} aria-label={record.institution_name}>
        <h2>{record.institution_name}</h2>
        <dl>
          <div><dt>Degree level</dt><dd>{record.degree_level}</dd></div>
          <div><dt>Major</dt><dd>{record.major}</dd></div>
          {record.minor && <div><dt>Minor</dt><dd>{record.minor}</dd></div>}
          <div><dt>Study year</dt><dd>{record.study_year}</dd></div>
          <div><dt>Start date</dt><dd>{record.start_date}</dd></div>
          <div><dt>Expected graduation</dt><dd>{months[record.expected_grad_month - 1]} {record.expected_grad_year}</dd></div>
          <div><dt>GPA</dt><dd>{record.gpa_value !== null && record.gpa_scale !== null ? `${record.gpa_value} / ${record.gpa_scale}` : "Not provided"}</dd></div>
          <div><dt>Include GPA on applications</dt><dd>{record.gpa_include_on_apps ? "Yes" : "No"}</dd></div>
          <div><dt>Primary</dt><dd>{record.is_primary ? "Yes" : "No"}</dd></div>
        </dl>
        <div className="auth-actions"><button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setEditor(record); setSuccess(""); }}>Edit</button>
          <button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setDeleting(record); setSuccess(""); }}>Delete</button></div>
        {deleting?.id === record.id && <div className="education-confirm" role="group" aria-label="Confirm deletion">
          <p>Delete {record.institution_name}? This permanently removes this education record.</p>
          <div className="auth-actions"><button className="primary" disabled={busy} onClick={() => { void remove(); }}>{busy ? "Deleting…" : "Confirm delete"}</button><button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel deletion</button></div>
        </div>}
      </article>)}</div>
    </>}
  </>;
}

function EducationForm({ record, onSave, onCancel }: { record?: Education; onSave: (record: Education) => void; onCancel: () => void }) {
  const { refresh } = useAuth();
  const [values, setValues] = useState(() => educationFormValues(record));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setError("");
    // Local validation gives actionable feedback without changing submitted facts.
    let create, changes;
    try { create = educationPayload(values); changes = record ? changedEducationFields(educationFormValues(record), values) : undefined; }
    catch (error) { setError(error instanceof Error ? error.message : "Check the entered facts."); return; }
    if (record && changes && Object.keys(changes).length === 0) { onCancel(); return; }
    setBusy(true);
    try { onSave(record ? await apiClient.updateEducation(record.id, changes!) : await apiClient.createEducation(create)); }
    catch (error) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    finally { setBusy(false); }
  }
  const text = (key: "institution_name" | "major" | "minor" | "start_date" | "expected_grad_year" | "gpa_value" | "gpa_scale", label: string, type = "text", required = false, maxLength?: number) => <div>
    <label htmlFor={key}>{label}</label><input id={key} name={key} type={type} required={required} maxLength={maxLength} min={key === "expected_grad_year" ? 2000 : undefined} max={key === "expected_grad_year" ? 2100 : undefined} inputMode={key.startsWith("gpa_") ? "decimal" : undefined} value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />
  </div>;
  return <form className="auth-card education-form" onSubmit={save} aria-busy={busy}>
    <h2>{record ? "Edit education" : "Add education"}</h2>
    <p className="muted">Enter your facts. Minor and GPA are optional. No GPA conversion is performed.</p>
    <fieldset disabled={busy}>
      {text("institution_name", "Institution name", "text", true, 255)}
      <label htmlFor="degree_level">Degree level</label><select id="degree_level" required value={values.degree_level} onChange={(event) => setValues({ ...values, degree_level: event.target.value })}><option value="">Select degree level</option>{degreeLevels.map((value) => <option key={value}>{value}</option>)}</select>
      {text("major", "Major", "text", true, 150)}{text("minor", "Minor", "text", false, 150)}
      <label htmlFor="study_year">Study year</label><select id="study_year" required value={values.study_year} onChange={(event) => setValues({ ...values, study_year: event.target.value })}><option value="">Select study year</option>{studyYears.map((value) => <option key={value}>{value}</option>)}</select>
      {text("start_date", "Start date", "date", true)}
      <label htmlFor="expected_grad_month">Expected graduation month</label><select id="expected_grad_month" required value={values.expected_grad_month} onChange={(event) => setValues({ ...values, expected_grad_month: event.target.value })}><option value="">Select month</option>{months.map((value, index) => <option value={index + 1} key={value}>{value}</option>)}</select>
      {text("expected_grad_year", "Expected graduation year", "number", true)}
      <div className="education-gpa">{text("gpa_value", "GPA value", "text", false, 6)}<span aria-hidden="true">/</span>{text("gpa_scale", "Native GPA scale", "text", false, 6)}</div>
      <p className="field-help">Use your original value and scale, with up to two decimal places. To remove GPA, clear both and disable inclusion.</p>
      <label className="education-checkbox"><input type="checkbox" checked={values.gpa_include_on_apps} onChange={(event) => setValues({ ...values, gpa_include_on_apps: event.target.checked })} />Include GPA on applications</label>
      <label className="education-checkbox"><input type="checkbox" checked={values.is_primary} onChange={(event) => setValues({ ...values, is_primary: event.target.checked })} />Primary education record</label>
      <p className="field-help">Selecting primary replaces your previous primary selection. Leaving all records unselected is allowed.</p>
    </fieldset>
    {error && <p role="alert" className="auth-error">{error}</p>}
    <div className="auth-actions"><button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save education"}</button><button className="secondary" disabled={busy} type="button" onClick={onCancel}>Cancel</button></div>
  </form>;
}
