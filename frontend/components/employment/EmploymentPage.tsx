"use client";

import Link from "next/link";
import { ReturnToReview } from "../onboarding/ReturnToReview";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, ApiError, authErrorMessage, type Employment } from "../../lib/api/client";
import { changedEmploymentFields, employmentFormValues, employmentPayload } from "../../lib/employment/form";
import { useAuth } from "../auth/AuthProvider";

export function EmploymentPage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell employment-shell">
    <Link href="/" className="brand">StudentSuccessful</Link><ReturnToReview />
    <h1 className="profile-title">Employment</h1>
    <p className="muted">Your work-history facts, entered by you. Employment location does not set job-search preferences.</p>
    {user === undefined ? (error ? <div><p role="alert">{error}</p><button className="primary" onClick={() => { void refresh().catch(() => {}); }}>Try again</button></div> : <p role="status">Checking your session…</p>)
      : user === null ? <p className="auth-footer">Please <Link href="/login">Login</Link> to view employment.</p>
      : <EmploymentContent key={user.id} />}
  </main>;
}

function EmploymentContent() {
  const { refresh } = useAuth();
  const [records, setRecords] = useState<Employment[] | null>(null);
  const [editor, setEditor] = useState<Employment | "new" | null>(null);
  const [deleting, setDeleting] = useState<Employment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    apiClient.listEmployment().then((items) => { if (active) setRecords(items); }).catch((error) => {
      if (active) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    });
    return () => { active = false; };
  }, [attempt, refresh]);

  async function remove() {
    if (!deleting || busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await apiClient.deleteEmployment(deleting.id);
      setRecords((current) => current?.filter((record) => record.id !== deleting.id) ?? null);
      setDeleting(null); setSuccess("Employment deleted.");
    } catch (error) {
      setError(authErrorMessage(error));
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    } finally { setBusy(false); }
  }

  function saved(record: Employment) {
    setRecords((current) => {
      const items = (current ?? []).map((item) => item.id === record.id ? record : item);
      return items.some((item) => item.id === record.id) ? items : [...items, record];
    });
    setEditor(null); setError(""); setSuccess("Employment saved.");
  }

  return <>
    {error && <div><p className="auth-error" role="alert">{error}</p><button className="secondary" onClick={() => { setEditor(null); setDeleting(null); setAttempt((value) => value + 1); }}>Reload list</button></div>}
    {success && <p className="profile-success" role="status">{success}</p>}
    {records === null && !error && <p role="status">Loading employment…</p>}
    {records !== null && <>
      {editor ? <EmploymentForm key={editor === "new" ? "new" : editor.id} record={editor === "new" ? undefined : editor} onSave={saved} onCancel={() => setEditor(null)} />
        : <button className="primary employment-add" disabled={busy || deleting !== null} onClick={() => { setEditor("new"); setSuccess(""); }}>Add employment</button>}
      {!records.length && <p className="muted">No employment records yet.</p>}
      <div className="employment-list">{records.map((record) => <article className="auth-card employment-record" key={record.id} aria-label={record.employer_name}>
        <h2>{record.employer_name}</h2>
        <dl>
          <div><dt>Job title</dt><dd>{record.job_title}</dd></div>
          {record.location && <div><dt>Location</dt><dd>{record.location}</dd></div>}
          <div><dt>Start date</dt><dd>{record.start_date}</dd></div>
          {record.end_date && <div><dt>End date</dt><dd>{record.end_date}</dd></div>}
          <div><dt>Currently employed</dt><dd>{record.currently_employed ? "Yes" : "No"}</dd></div>
        </dl>
        {record.description && <div className="employment-description"><h3>Description</h3><p>{record.description}</p></div>}
        <div className="auth-actions"><button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setEditor(record); setSuccess(""); }}>Edit</button>
          <button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setDeleting(record); setSuccess(""); }}>Delete</button></div>
        {deleting?.id === record.id && <div className="employment-confirm" role="group" aria-label="Confirm deletion">
          <p>Delete {record.employer_name}? This permanently removes this employment record.</p>
          <div className="auth-actions"><button className="primary" disabled={busy} onClick={() => { void remove(); }}>{busy ? "Deleting…" : "Confirm delete"}</button><button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel deletion</button></div>
        </div>}
      </article>)}</div>
    </>}
  </>;
}

function EmploymentForm({ record, onSave, onCancel }: { record?: Employment; onSave: (record: Employment) => void; onCancel: () => void }) {
  const { refresh } = useAuth();
  const [values, setValues] = useState(() => employmentFormValues(record));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setError("");
    let create, changes;
    try { create = employmentPayload(values); changes = record ? changedEmploymentFields(employmentFormValues(record), values) : undefined; }
    catch (error) { setError(error instanceof Error ? error.message : "Check the entered facts."); return; }
    if (record && changes && Object.keys(changes).length === 0) { onCancel(); return; }
    setBusy(true);
    try { onSave(record ? await apiClient.updateEmployment(record.id, changes!) : await apiClient.createEmployment(create)); }
    catch (error) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    finally { setBusy(false); }
  }
  const input = (key: "employer_name" | "job_title" | "location" | "start_date" | "end_date", label: string, type = "text", required = false, maxLength?: number) => <div>
    <label htmlFor={key}>{label}</label><input id={key} name={key} type={type} required={required} maxLength={maxLength} value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />
  </div>;
  return <form className="auth-card employment-form" onSubmit={save} aria-busy={busy}>
    <h2>{record ? "Edit employment" : "Add employment"}</h2>
    <p className="muted">Enter your work-history facts. Location and description are optional.</p>
    <fieldset disabled={busy}>
      {input("employer_name", "Employer name", "text", true, 255)}
      {input("job_title", "Job title", "text", true, 150)}
      {input("location", "Location", "text", false, 150)}
      {input("start_date", "Start date", "date", true)}
      <label className="employment-checkbox"><input type="checkbox" checked={values.currently_employed} onChange={(event) => setValues({ ...values, currently_employed: event.target.checked })} />Currently employed</label>
      {input("end_date", "End date", "date", !values.currently_employed)}
      <p className="field-help">End date is required for a completed role. A current role may keep a known end date; checking Currently employed does not erase it.</p>
      <label htmlFor="description">Description</label><textarea id="description" name="description" rows={5} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} />
    </fieldset>
    {error && <p role="alert" className="auth-error">{error}</p>}
    <div className="auth-actions"><button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save employment"}</button><button className="secondary" disabled={busy} type="button" onClick={onCancel}>Cancel</button></div>
  </form>;
}
