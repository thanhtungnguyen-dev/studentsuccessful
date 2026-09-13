"use client";

import Link from "next/link";
import { ReturnToReview } from "../onboarding/ReturnToReview";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, ApiError, authErrorMessage, type WorkAuthorization } from "../../lib/api/client";
import { STATUS_LABELS, changedWorkAuthorizationFields, workAuthorizationFormValues, workAuthorizationPayload, type WorkAuthorizationFormValues } from "../../lib/work-authorization/form";
import { useAuth } from "../auth/AuthProvider";

export function WorkAuthorizationPage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell work-authorization-shell">
    <Link href="/" className="brand">StudentSuccessful</Link><ReturnToReview />
    <h1 className="profile-title">Work Authorization</h1>
    <p className="muted">Enter your authorization facts for each country. Country and status do not set job-search preferences or determine sponsorship answers.</p>
    {user === undefined ? (error ? <div><p role="alert">{error}</p><button className="primary" onClick={() => { void refresh().catch(() => {}); }}>Try again</button></div> : <p role="status">Checking your session…</p>)
      : user === null ? <p className="auth-footer">Please <Link href="/login">Login</Link> to view work authorization.</p>
      : <WorkAuthorizationContent key={user.id} />}
  </main>;
}

function WorkAuthorizationContent() {
  const { refresh } = useAuth();
  const [records, setRecords] = useState<WorkAuthorization[] | null>(null);
  const [editor, setEditor] = useState<WorkAuthorization | "new" | null>(null);
  const [deleting, setDeleting] = useState<WorkAuthorization | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError("");
    apiClient.listWorkAuthorizations().then((items) => { if (active) setRecords(items); }).catch((error) => {
      if (active) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    });
    return () => { active = false; };
  }, [attempt, refresh]);

  async function remove() {
    if (!deleting || busy) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      await apiClient.deleteWorkAuthorization(deleting.id);
      setRecords((current) => current?.filter((record) => record.id !== deleting.id) ?? null);
      setDeleting(null); setSuccess("Work authorization deleted.");
    } catch (error) {
      setError(authErrorMessage(error));
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    } finally { setBusy(false); }
  }

  function saved(record: WorkAuthorization) {
    setRecords((current) => {
      const items = (current ?? []).map((item) => item.id === record.id ? record : item);
      return (items.some((item) => item.id === record.id) ? items : [...items, record]).sort((a, b) => a.country_code.localeCompare(b.country_code) || a.id.localeCompare(b.id));
    });
    setEditor(null); setError(""); setSuccess("Work authorization saved.");
  }

  return <>
    {error && <div><p className="auth-error" role="alert">{error}</p><button className="secondary" onClick={() => { setEditor(null); setDeleting(null); setAttempt((value) => value + 1); }}>Reload list</button></div>}
    {success && <p className="profile-success" role="status">{success}</p>}
    {records === null && !error && <p role="status">Loading work authorization…</p>}
    {records !== null && <>
      {editor ? <WorkAuthorizationForm key={editor === "new" ? "new" : editor.id} record={editor === "new" ? undefined : editor} onSave={saved} onCancel={() => setEditor(null)} />
        : <button className="primary work-authorization-add" disabled={busy || deleting !== null} onClick={() => { setEditor("new"); setSuccess(""); }}>Add country authorization</button>}
      {!records.length && <p className="muted">No work authorization records yet.</p>}
      <div className="work-authorization-list">{records.map((record) => <article className="auth-card work-authorization-record" key={record.id} aria-label={record.country_code}>
        <h2>{record.country_code}</h2>
        <dl>
          <div><dt>Authorization status</dt><dd>{STATUS_LABELS[record.authorization_status]}</dd></div>
          <div><dt>Current sponsorship required?</dt><dd>{record.requires_current_sponsorship ? "Yes" : "No"}</dd></div>
          <div><dt>Future sponsorship required?</dt><dd>{record.requires_future_sponsorship ? "Yes" : "No"}</dd></div>
          <div><dt>Last confirmed (UTC)</dt><dd><time dateTime={record.last_confirmed_at}>{record.last_confirmed_at.replace("T", " ")}</time></dd></div>
        </dl>
        {record.notes && <div className="work-authorization-notes"><h3>Notes</h3><p>{record.notes}</p></div>}
        <div className="auth-actions"><button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setEditor(record); setSuccess(""); }}>Edit</button>
          <button className="secondary" disabled={busy || editor !== null || deleting !== null} onClick={() => { setDeleting(record); setSuccess(""); }}>Delete</button></div>
        {deleting?.id === record.id && <div className="work-authorization-confirm" role="group" aria-label="Confirm deletion">
          <p>Delete {record.country_code}? This permanently removes this work authorization record.</p>
          <div className="auth-actions"><button className="primary" disabled={busy} onClick={() => { void remove(); }}>{busy ? "Deleting…" : "Confirm delete"}</button><button className="secondary" disabled={busy} onClick={() => setDeleting(null)}>Cancel deletion</button></div>
        </div>}
      </article>)}</div>
    </>}
  </>;
}

function WorkAuthorizationForm({ record, onSave, onCancel }: { record?: WorkAuthorization; onSave: (record: WorkAuthorization) => void; onCancel: () => void }) {
  const { refresh } = useAuth();
  const [values, setValues] = useState(() => workAuthorizationFormValues(record));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (busy) return;
    setError("");
    let create, changes;
    try { create = workAuthorizationPayload(values); changes = record ? changedWorkAuthorizationFields(workAuthorizationFormValues(record), values) : undefined; }
    catch (error) { setError(error instanceof Error ? error.message : "Check the entered facts."); return; }
    if (record && changes && Object.keys(changes).length === 0) { onCancel(); return; }
    setBusy(true);
    try { onSave(record ? await apiClient.updateWorkAuthorization(record.id, changes!) : await apiClient.createWorkAuthorization(create)); }
    catch (error) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    finally { setBusy(false); }
  }
  const choice = (key: "requires_current_sponsorship" | "requires_future_sponsorship", label: string) => <div>
    <label htmlFor={key}>{label}</label><select id={key} required value={values[key]} onChange={(event) => setValues({ ...values, [key]: event.target.value as "" | "yes" | "no" })}>
      <option value="">Choose an answer</option><option value="yes">Yes</option><option value="no">No</option>
    </select>
  </div>;
  return <form className="auth-card work-authorization-form" onSubmit={save} aria-busy={busy}>
    <h2>{record ? "Edit work authorization" : "Add country authorization"}</h2>
    <p className="muted">Supply each fact explicitly. Status does not determine your sponsorship answers.</p>
    <fieldset disabled={busy}>
      <label htmlFor="country_code">Country code</label><input id="country_code" required maxLength={2} pattern="[A-Za-z]{2}" placeholder="e.g. CA" value={values.country_code} onChange={(event) => setValues({ ...values, country_code: event.target.value })} />
      <p className="field-help">Country whose authorization you are describing. Two letters, such as CA or US; this control validates format only.</p>
      <label htmlFor="authorization_status">Authorization status</label><select id="authorization_status" required value={values.authorization_status} onChange={(event) => setValues({ ...values, authorization_status: event.target.value as WorkAuthorizationFormValues["authorization_status"] })}>
        <option value="">Choose a status</option>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select>
      {choice("requires_current_sponsorship", "Requires sponsorship now?")}
      {choice("requires_future_sponsorship", "Requires sponsorship in future?")}
      <label htmlFor="notes">Optional notes</label><textarea id="notes" rows={3} maxLength={255} value={values.notes} onChange={(event) => setValues({ ...values, notes: event.target.value })} />
      <p className="field-help">Optional note. Do not enter passport, visa, permit, SIN/SSN, or other government document numbers.</p>
    </fieldset>
    {error && <p role="alert" className="auth-error">{error}</p>}
    <div className="auth-actions"><button className="primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save work authorization"}</button><button className="secondary" disabled={busy} type="button" onClick={onCancel}>Cancel</button></div>
  </form>;
}
