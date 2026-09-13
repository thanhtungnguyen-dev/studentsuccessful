"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type JobAlert,
  type JobAlertInbox,
  type PublicJobDetail,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { JobDetail, JobDetailFailure } from "../jobs/JobsPage";
import { MarkAsApplied } from "../applications/MarkAsApplied";
import { safeApplicationUrl } from "../../lib/jobs/applicationUrl";

type AlertGroup = {
  key: string;
  label: string;
  items: JobAlert[];
};

function alertGroups(items: JobAlert[]): AlertGroup[] {
  const groups = new Map<string, AlertGroup>();
  for (const alert of items) {
    const isDigest = alert.delivery_mode !== "INSTANT";
    const key = isDigest
      ? [alert.delivery_mode, alert.saved_search_id, alert.scheduled_for].join(":")
      : alert.id;
    const mode = alert.delivery_mode === "HOURLY_DIGEST" ? "Hourly digest" : "Daily digest";
    const label = isDigest
      ? `${mode} · new jobs matched "${alert.saved_search_name}"`
      : `New job matched "${alert.saved_search_name}"`;
    const current = groups.get(key);
    if (current) current.items.push(alert);
    else groups.set(key, { key, label, items: [alert] });
  }
  return [...groups.values()];
}

function AlertItem({
  alert,
  pending,
  onView,
  onMarkRead,
}: {
  alert: JobAlert;
  pending: boolean;
  onView: () => void;
  onMarkRead: () => void;
}) {
  const application = safeApplicationUrl(alert.application_url);
  return (
    <article className="alert-card">
      {!alert.read_at ? <p className="alert-unread">Unread · NEW JOB</p> : <p className="muted">NEW JOB</p>}
      <strong>{alert.title}</strong>
      <p className="muted">
        {[alert.company_name, ...alert.locations, alert.work_mode, alert.employment_type]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p className="muted">First seen {alert.first_seen_at}</p>
      <div className="job-actions">
        <button className="secondary" type="button" disabled={pending} onClick={onView}>View</button>
        {application ? (
          <a className="secondary" href={application} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">
            Apply
          </a>
        ) : null}
        <MarkAsApplied canonicalJobId={alert.canonical_job_id} jobTitle={alert.title} />
        {!alert.read_at ? (
          <button className="secondary" type="button" disabled={pending} onClick={onMarkRead}>Mark read</button>
        ) : null}
      </div>
    </article>
  );
}

export function AlertInbox({
  inbox,
  pendingAlertIds,
  onView,
  onMarkRead,
}: {
  inbox: JobAlertInbox;
  pendingAlertIds: Set<string>;
  onView: (alert: JobAlert) => void;
  onMarkRead: (alert: JobAlert) => void;
}) {
  const groups = useMemo(() => alertGroups(inbox.items), [inbox.items]);
  if (!groups.length) {
    return (
      <section className="auth-card dashboard-card">
        <h2>Alerts</h2>
        <p className="muted">No delivered job alerts yet. Enable alerts on a saved search to hear about future matching jobs.</p>
        <Link className="secondary" href="/jobs">Open saved searches</Link>
      </section>
    );
  }
  return (
    <section className="auth-card dashboard-card">
      <header>
        <h2>Alerts</h2>
        <p className="alerts-unread-count">{inbox.unread_count} unread</p>
      </header>
      <ul className="alerts-list">
        {groups.map((group) => (
          <li className="alerts-group" key={group.key}>
            <h3>{group.label}</h3>
            {group.items.length > 1 ? <p className="muted">{group.items.length} new canonical jobs</p> : null}
            <ul className="alerts-group-list">
              {group.items.map((alert) => (
                <li key={alert.id}>
                  <AlertItem
                    alert={alert}
                    pending={pendingAlertIds.has(alert.id)}
                    onView={() => onView(alert)}
                    onMarkRead={() => onMarkRead(alert)}
                  />
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function AlertsPage() {
  const { user, error: sessionError, refresh } = useAuth();
  const [inbox, setInbox] = useState<JobAlertInbox | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [pendingAlertIds, setPendingAlertIds] = useState<Set<string>>(() => new Set());
  const [detail, setDetail] = useState<PublicJobDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);

  function handleError(reason: unknown) {
    setError(authErrorMessage(reason));
    if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
  }

  function applyRead(id: string, readAt: string) {
    setInbox((current) => current === null ? null : {
      unread_count: Math.max(0, current.unread_count - (current.items.find((item) => item.id === id)?.read_at ? 0 : 1)),
      items: current.items.map((item) => item.id === id ? { ...item, read_at: readAt } : item),
    });
  }

  async function markRead(alert: JobAlert) {
    if (alert.read_at) return;
    setPendingAlertIds((current) => new Set(current).add(alert.id));
    setError("");
    try {
      const state = await apiClient.markAlertRead(alert.id);
      applyRead(state.id, state.read_at);
    } catch (reason) {
      handleError(reason);
    } finally {
      setPendingAlertIds((current) => {
        const next = new Set(current);
        next.delete(alert.id);
        return next;
      });
    }
  }

  async function viewAlert(alert: JobAlert) {
    setSelectedAlertId(alert.id);
    setDetail(null);
    setDetailError("");
    setError("");
    setPendingAlertIds((current) => new Set(current).add(alert.id));
    try {
      if (!alert.read_at) {
        const state = await apiClient.markAlertRead(alert.id);
        applyRead(state.id, state.read_at);
      }
      setDetail(await apiClient.getJob(alert.canonical_job_id));
    } catch (reason) {
      const message = authErrorMessage(reason);
      setDetailError(message);
      if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
    } finally {
      setPendingAlertIds((current) => {
        const next = new Set(current);
        next.delete(alert.id);
        return next;
      });
    }
  }

  useEffect(() => {
    if (!user) return;
    let active = true;
    setInbox(null);
    setError("");
    apiClient.listAlerts()
      .then((next) => {
        if (active) setInbox(next);
      })
      .catch((reason) => {
        if (active) handleError(reason);
      });
    return () => {
      active = false;
    };
  }, [attempt, user]);

  return (
    <main className="auth-shell dashboard-shell alerts-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <h1 className="profile-title">Alerts</h1>
      <p className="muted">New canonical jobs matched by your alert-enabled saved searches.</p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view alerts.</p>
            : error && inbox === null ? (
              <section className="auth-card dashboard-card">
                <p role="alert" className="auth-error">Could not load alerts. {error}</p>
                <button className="secondary" type="button" onClick={() => setAttempt((value) => value + 1)}>Retry alerts</button>
              </section>
            ) : inbox === null ? <p role="status">Loading alerts…</p>
              : (
                <>
                  {error ? <p role="alert" className="auth-error">{error}</p> : null}
                  <AlertInbox
                    inbox={inbox}
                    pendingAlertIds={pendingAlertIds}
                    onView={(alert) => void viewAlert(alert)}
                    onMarkRead={(alert) => void markRead(alert)}
                  />
                  {selectedAlertId ? (
                    <section className="alerts-detail">
                      <button className="secondary" type="button" onClick={() => { setSelectedAlertId(null); setDetail(null); setDetailError(""); }}>
                        Back to alerts
                      </button>
                      {detailError ? <JobDetailFailure message={detailError} retry={() => {
                        const alert = inbox.items.find((item) => item.id === selectedAlertId);
                        if (alert) void viewAlert(alert);
                      }} />
                        : detail ? <JobDetail job={detail} /> : <p role="status">Loading job details…</p>}
                    </section>
                  ) : null}
                </>
              )}
    </main>
  );
}
