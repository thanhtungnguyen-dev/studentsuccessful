"use client";

import Link from "next/link";
import { ReturnToReview } from "../onboarding/ReturnToReview";
import { useEffect, useState, type FormEvent } from "react";
import { apiClient, ApiError, authErrorMessage } from "../../lib/api/client";
import { changedProfileFields, profileFormValues, profileSections, type ProfileFormValues } from "../../lib/profile/form";
import { useAuth } from "../auth/AuthProvider";

export function ProfilePage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell profile-shell">
    <Link href="/" className="brand">StudentSuccessful</Link><ReturnToReview />
    <h1 className="profile-title">Application Profile</h1>
    <p className="muted">Facts you choose to use on applications. These do not set your job-search preferences.</p>
    {user === undefined ? (error ? <div><p role="alert">{error}</p><button className="primary" onClick={() => { void refresh().catch(() => {}); }}>Try again</button></div> : <p role="status">Checking your session…</p>)
      : user === null ? <p className="auth-footer">Please <Link href="/login">Login</Link> to view your profile.</p>
      : <ProfileForm key={user.id} />}
  </main>;
}

function ProfileForm() {
  const { refresh } = useAuth();
  const [values, setValues] = useState<ProfileFormValues | null>(null);
  const [original, setOriginal] = useState<ProfileFormValues | null>(null);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError("");
    apiClient.getProfile().then((profile) => {
      if (active) { const fields = profileFormValues(profile); setOriginal(fields); setValues(fields); }
    }).catch((error) => {
      if (active) {
        setError(authErrorMessage(error));
        if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
      }
    });
    return () => { active = false; };
  }, [attempt, refresh]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!values || !original || busy) return;
    setError(""); setSuccess("");
    if (!values.legal_first_name.trim() || !values.legal_last_name.trim()) {
      setError("Enter your legal first and last names as you intend to use them on applications."); return;
    }
    const changes = changedProfileFields(original, values);
    if (Object.keys(changes).length === 0) { setSuccess("No changes to save."); return; }
    setBusy(true);
    try {
      const profile = await apiClient.updateProfile(changes);
      const fields = profileFormValues(profile);
      setValues(fields); setOriginal(fields); setSuccess("Profile saved.");
    } catch (error) {
      setError(authErrorMessage(error));
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    } finally { setBusy(false); }
  }

  if (!values) return error ? <div className="auth-card"><p role="alert" className="auth-error">{error}</p><button className="primary" onClick={() => setAttempt((value) => value + 1)}>Retry loading</button></div> : <p role="status">Loading profile…</p>;
  return <form onSubmit={save} className="auth-card profile-form" aria-busy={busy}>
    <p className="muted">Legal first and last names are required. Everything else is optional. Clear an optional field to remove it.</p>
    {profileSections.map((section) => <fieldset key={section.title} disabled={busy}>
      <legend>{section.title}</legend>
      {section.fields.map((field) => <div key={field.key}>
        <label htmlFor={field.key}>{field.label}{field.required ? " (required)" : ""}</label>
        {field.multiline ? <textarea id={field.key} name={field.key} rows={3} maxLength={field.maxLength} value={values[field.key]} onChange={(event) => { setValues({ ...values, [field.key]: event.target.value }); setSuccess(""); }} />
          : <input id={field.key} name={field.key} type={field.type ?? "text"} required={field.required} maxLength={field.maxLength} value={values[field.key]} aria-describedby={field.help ? `${field.key}-help` : undefined} onChange={(event) => { setValues({ ...values, [field.key]: event.target.value }); setSuccess(""); }} />}
        {field.help && <p id={`${field.key}-help`} className="field-help">{field.help}</p>}
      </div>)}
    </fieldset>)}
    {error && <p role="alert" className="auth-error">{error}</p>}
    {success && <p role="status" className="profile-success">{success}</p>}
    <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
    {error && <p className="auth-footer"><Link href="/login">Login again</Link></p>}
  </form>;
}
