"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import {
  apiClient,
  authErrorMessage,
  type Application,
} from "../../lib/api/client";

type ResumeOption = {
  id: string;
  label: string;
};

export function MarkAsApplied({
  canonicalJobId,
  jobTitle,
  tracked = false,
  onTracked,
}: {
  canonicalJobId: string;
  jobTitle: string;
  tracked?: boolean;
  onTracked?: (application: Application) => void;
}) {
  const [open, setOpen] = useState(false);
  const [resumeOptions, setResumeOptions] = useState<ResumeOption[]>([]);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [resumeVersionId, setResumeVersionId] = useState("");
  const [appliedDate, setAppliedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Application | null>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setResumeLoading(true);
    setError("");
    apiClient.listResumes()
      .then(async (resumes) => {
        const groups = await Promise.all(
          resumes.map(async (resume) => {
            const versions = await apiClient.listResumeVersions(resume.id);
            return versions.map((version) => ({
              id: version.id,
              label: resume.title + " · v" + version.version_number,
            }));
          }),
        );
        if (active) setResumeOptions(groups.flat());
      })
      .catch((reason) => {
        if (active) setError(authErrorMessage(reason));
      })
      .finally(() => {
        if (active) setResumeLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const application = await apiClient.createApplication({
        canonical_job_id: canonicalJobId,
        ...(resumeVersionId ? { resume_version_id: resumeVersionId } : {}),
        ...(appliedDate ? { applied_at: new Date(appliedDate + "T12:00:00.000Z").toISOString() } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      });
      setCreated(application);
      setOpen(false);
      onTracked?.(application);
    } catch (reason) {
      setError(authErrorMessage(reason));
    } finally {
      setBusy(false);
    }
  }

  if (tracked || created) {
    return <Link className="secondary" href="/applications">Tracked: {created?.current_status ?? "Applied"}</Link>;
  }

  return (
    <>
      <button className="secondary" type="button" onClick={() => setOpen(true)}>Mark as Applied</button>
      {open ? (
        <section className="application-confirmation" aria-label={"Track " + jobTitle}>
          <h3>Mark as Applied</h3>
          <p className="muted">Confirm only after you submitted an application yourself. Opening Apply never records an application.</p>
          <form className="application-form" onSubmit={submit}>
            <label>
              Resume version used (optional)
              <select value={resumeVersionId} onChange={(event) => setResumeVersionId(event.currentTarget.value)} disabled={resumeLoading}>
                <option value="">No StudentSuccessful resume selected</option>
                {resumeOptions.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Applied date (optional)
              <input type="date" value={appliedDate} onChange={(event) => setAppliedDate(event.currentTarget.value)} />
            </label>
            <label>
              Private note (optional)
              <textarea value={notes} maxLength={2000} onChange={(event) => setNotes(event.currentTarget.value)} />
            </label>
            {error ? <p role="alert" className="auth-error">{error}</p> : null}
            <div className="job-actions">
              <button className="primary" type="submit" disabled={busy}>{busy ? "Saving…" : "Confirm: Mark as Applied"}</button>
              <button className="secondary" type="button" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
            </div>
          </form>
        </section>
      ) : null}
    </>
  );
}
