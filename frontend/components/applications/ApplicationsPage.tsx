"use client";
import { LoadingState } from "../ui/LoadingState";

import Link from "next/link";
import { PageHeader } from "../ui/PageHeader";
import { CompanyLogo } from "../jobs/CompanyLogo";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type Application,
  type ApplicationFilterStatus,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { safeApplicationUrl } from "../../lib/jobs/applicationUrl";

type StatusFilter = NonNullable<ApplicationFilterStatus>;
type ApplicationStatus = Exclude<StatusFilter, "ALL">;

const filters: Array<{ value: StatusFilter; label: string }> = [
  { value: "ALL", label: "All" },
  { value: "APPLIED", label: "Applied" },
  { value: "INTERVIEW", label: "Interview" },
  { value: "OFFER", label: "Offer" },
  { value: "REJECTED", label: "Rejected" },
  { value: "WITHDRAWN", label: "Withdrawn" },
];

function readableStatus(value: string): string {
  return value.slice(0, 1) + value.slice(1).toLowerCase();
}

function dateLabel(value: string | null): string {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function ApplicationCard({
  application,
  pending,
  onStatus,
  onSaveNotes,
}: {
  application: Application;
  pending: boolean;
  onStatus: (status: ApplicationStatus, note: string) => void;
  onSaveNotes: (notes: string) => void;
}) {
  const [transitionNote, setTransitionNote] = useState("");
  const [nextStatus, setNextStatus] = useState<ApplicationStatus>(application.current_status);
  useEffect(() => { setNextStatus(application.current_status); setTransitionNote(""); }, [application.current_status]);
  const [notes, setNotes] = useState(application.notes ?? "");
  const apply = application.application_url
    ? safeApplicationUrl(application.application_url)
    : null;
  const history = application.history ?? [];
  return (
    <article className="application-card">
      <header>
        <div className="application-identity">
          <CompanyLogo company={application.company_name} />
          <div>
            <h2>{application.job_title}</h2>
            <p className="muted">{application.company_name}</p>
          </div>
        </div>
        <p className="application-status" data-status={application.current_status}>{readableStatus(application.current_status)}</p>
      </header>
      <dl>
        <div><dt>Applied</dt><dd>{dateLabel(application.applied_at)}</dd></div>
        <div><dt>Resume</dt><dd>{application.resume_title ? application.resume_title + (application.resume_version_number ? " · v" + application.resume_version_number : "") : "Not recorded"}</dd></div>
        <div><dt>Listing</dt><dd>{application.job_lifecycle === "CLOSED" ? "Listing closed · still in your tracker." : "Listing on record"}</dd></div>
      </dl>
      <div className="application-actions">
        <label>
          Update status
          <select
            aria-label={"Update status for " + application.job_title}
            value={nextStatus}
            disabled={pending}
            onChange={(event) => setNextStatus(event.currentTarget.value as ApplicationStatus)}
          >
            {filters.filter((option) => option.value !== "ALL").map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label>
          Transition note (optional)
          <input value={transitionNote} maxLength={2000} disabled={pending} placeholder="Add context for this update" onChange={(event) => setTransitionNote(event.currentTarget.value)} />
        </label>
        <button className="primary application-status-save" type="button" disabled={pending || nextStatus === application.current_status} onClick={() => onStatus(nextStatus, transitionNote)}>
          {pending ? "Saving…" : "Save status"}
        </button>
        {apply ? <a className="secondary" href={apply} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">View original listing</a> : null}
      </div>
      <details className="application-disclosure"><summary>Notes and status history</summary>
      <label className="application-notes">
        Private note
        <textarea value={notes} maxLength={2000} disabled={pending} onChange={(event) => setNotes(event.currentTarget.value)} />
      </label>
      <button className="secondary" type="button" disabled={pending || notes === (application.notes ?? "")} onClick={() => onSaveNotes(notes)}>
        Save note
      </button>
      <section className="application-history">
        <h3>Status history</h3>
        <ol>
          {history.map((event) => (
            <li key={event.id}>
              <strong>{event.previous_status ? readableStatus(event.previous_status) + " → " : ""}{readableStatus(event.new_status)}</strong>
              <span>{dateLabel(event.transitioned_at)}</span>
              {event.notes ? <p>{event.notes}</p> : null}
            </li>
          ))}
        </ol>
      </section>
      </details>
    </article>
  );
}

export function ApplicationsPage() {
  const { user, error: sessionError, refresh } = useAuth();
  const [filter, setFilter] = useState<StatusFilter>("ALL");
  const [items, setItems] = useState<Application[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [pendingIds, setPendingIds] = useState<Set<string>>(() => new Set());

  function handleError(reason: unknown) {
    setError(authErrorMessage(reason));
    if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
  }

  function replace(application: Application) {
    setItems((current) => current?.flatMap((item) =>
      item.id !== application.id ? [item]
        : filter === "ALL" || filter === application.current_status ? [application] : []
    ) ?? current);
  }

  async function updateStatus(application: Application, status: ApplicationStatus, statusNote: string) {
    setPendingIds((current) => new Set(current).add(application.id));
    setError("");
    try {
      replace(await apiClient.updateApplication(application.id, {
        expected_version: application.version,
        status,
        ...(statusNote.trim() ? { status_note: statusNote.trim() } : {}),
      }));
    } catch (reason) {
      handleError(reason);
      if (reason instanceof ApiError && reason.status === 409) setAttempt((value) => value + 1);
    } finally {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(application.id);
        return next;
      });
    }
  }

  async function saveNotes(application: Application, notes: string) {
    setPendingIds((current) => new Set(current).add(application.id));
    setError("");
    try {
      replace(await apiClient.updateApplication(application.id, {
        expected_version: application.version,
        notes: notes.trim() || null,
      }));
    } catch (reason) {
      handleError(reason);
      if (reason instanceof ApiError && reason.status === 409) setAttempt((value) => value + 1);
    } finally {
      setPendingIds((current) => {
        const next = new Set(current);
        next.delete(application.id);
        return next;
      });
    }
  }

  useEffect(() => {
    if (!user) return;
    let active = true;
    setLoading(true);
    setError("");
    apiClient.listApplications(filter)
      .then((next) => {
        if (active) setItems(next);
      })
      .catch((reason) => {
        if (active) handleError(reason);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false;
    };
  }, [attempt, filter, user]);

  return (
    <main className="auth-shell dashboard-shell applications-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <PageHeader title="Applications" description="Track applications you have submitted, update their status, and keep notes." />
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <LoadingState label="Checking your session…" />
          : user === null ? <p>Please <Link href="/login">Login</Link> to view applications.</p>
            : (
              <>
                <nav className="application-filters" aria-label="Application status">
                  {filters.map((option) => (
                    <button
                      className="secondary"
                      type="button"
                      key={option.value}
                      aria-pressed={filter === option.value}
                      onClick={() => setFilter(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </nav>
                {loading && items !== null && <div className="applications-refresh" role="status"><span className="sr-only">Updating applications</span></div>}
                {error && items !== null ? <p role="alert" className="auth-error">{error}</p> : null}
                {items === null ? (
                  error ? (
                    <section className="auth-card dashboard-card">
                      <p role="alert" className="auth-error">Could not load applications. {error}</p>
                      <button className="secondary" type="button" onClick={() => setAttempt((value) => value + 1)}>Retry applications</button>
                    </section>
                  ) : <LoadingState label="Loading applications…" />
                ) : !items.length ? (
                  <section className="auth-card dashboard-card">
                    <h2>{filter === "ALL" ? "No applications yet" : "No applications at this stage"}</h2>
                    <p className="muted">{filter === "ALL" ? "After applying on an employer's site, add the role to your tracker." : "Choose another status above to see your other applications."}</p>
                    {filter === "ALL" && <Link className="secondary" href="/jobs">Browse jobs</Link>}
                  </section>
                ) : (
                  <section className="applications-list" aria-busy={loading} style={{ opacity: loading ? 0.68 : 1, transition: "opacity 140ms ease" }}>
                    {items.map((application) => (
                      <ApplicationCard
                        key={application.id}
                        application={application}
                        pending={pendingIds.has(application.id)}
                        onStatus={(status, note) => void updateStatus(application, status, note)}
                        onSaveNotes={(notes) => void saveNotes(application, notes)}
                      />
                    ))}
                  </section>
                )}
              </>
            )}
    </main>
  );
}
