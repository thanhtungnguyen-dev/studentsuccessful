"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type ResumeTailoringDraft,
  type ResumeVersion,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type DraftItem = NonNullable<ResumeTailoringDraft["keep"]>[number];
type CandidateSource = NonNullable<DraftItem["sources"]>[number];
type ResumeChoice = { resumeId: string; resumeTitle: string; version: ResumeVersion };
type DraftResponse = {
  ownerId: string;
  jobId: string;
  resumeVersionId: string;
  draft: ResumeTailoringDraft;
};

function selectedVersionFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const values = new URLSearchParams(window.location.search).getAll("resume_version_id");
  return values.length === 1 && values[0] ? values[0] : null;
}

function sourceLabel(source: CandidateSource, selectedVersionId: string): string {
  if (source.source_type === "CONFIRMED_BY_USER") {
    return "Confirmed by you — recorded candidate skill source.";
  }
  if (source.source_type === "RESUME_EVIDENCE") {
    const resume = source.resume_title || "resume";
    const version = source.resume_version_number === null || source.resume_version_number === undefined
      ? "" : `, version ${source.resume_version_number}`;
    const ordinal = source.evidence_ordinal === null || source.evidence_ordinal === undefined
      ? "" : `, evidence item ${source.evidence_ordinal}`;
    const selected = source.resume_version_id === selectedVersionId;
    return `${resume}${version}${ordinal} — parser-recognized resume evidence${selected
      ? " on the selected resume version."
      : " is outside the selected resume version and is not used for a draft."}`;
  }
  return `${source.project_title || "Project"} — recorded project technology source.`;
}

function CopyDraftButton({ draftText }: { draftText: string }) {
  const [message, setMessage] = useState("");

  async function copyDraftText() {
    try {
      await navigator.clipboard.writeText(draftText);
      setMessage("Copied draft text");
    } catch {
      setMessage("Copy unavailable; select the draft text manually.");
    }
  }

  return (
    <div className="draft-copy">
      <button className="secondary" onClick={() => void copyDraftText()}>Copy draft text</button>
      {message && <p role="status" className="muted">{message}</p>}
    </div>
  );
}

export function ResumeTailoringDraftAction({
  item,
  selectedVersionId,
}: {
  item: DraftItem;
  selectedVersionId: string;
}) {
  const sources = item.sources ?? [];
  return (
    <article className="draft-action">
      <header>
        <h3>{item.name}</h3>
        <p className="muted">{item.category}{item.importance ? ` · ${item.importance}` : ""}</p>
      </header>
      {item.description && <p className="draft-description">{item.description}</p>}
      <p className="muted"><strong>Phase 15 action:</strong> {item.action}</p>
      <p><strong>Why:</strong> {item.reason}</p>
      <p><strong>Safety boundary:</strong> {item.limitation}</p>
      {item.draft_text && (
        <>
          <h4>Draft text</h4>
          <p className="draft-text">{item.draft_text}</p>
          <CopyDraftButton draftText={item.draft_text} />
        </>
      )}
      {sources.length ? (
        <>
          <h4>Recorded sources</h4>
          <ul className="draft-sources">
            {sources.map((source) => (
              <li key={`${source.source_type}-${source.source_id}`}>
                {sourceLabel(source, selectedVersionId)}
              </li>
            ))}
          </ul>
        </>
      ) : <p className="muted">No eligible recorded source is used for a draft.</p>}
    </article>
  );
}

function ResumeTailoringDraftGroup({
  title,
  intro,
  items,
  empty,
  selectedVersionId,
}: {
  title: string;
  intro: string;
  items: DraftItem[];
  empty: string;
  selectedVersionId: string;
}) {
  return (
    <section className="auth-card dashboard-card draft-group">
      <h2>{title}</h2>
      <p className="muted">{intro}</p>
      {items.length ? items.map((item, index) => (
        <ResumeTailoringDraftAction
          key={`${item.category}-${item.requirement_id}-${index}`}
          item={item}
          selectedVersionId={selectedVersionId}
        />
      )) : <p className="muted">{empty}</p>}
    </section>
  );
}

export function ResumeTailoringDraftContent({ draft }: { draft: ResumeTailoringDraft }) {
  return (
    <>
      <section className="auth-card dashboard-card draft-introduction">
        <h1 className="profile-title">Resume Tailoring Draft</h1>
        <p className="fit-job">{draft.job_title}{draft.company_name ? ` · ${draft.company_name}` : ""}</p>
        <p className="draft-version"><strong>Selected resume:</strong> {draft.resume_title}, version {draft.resume_version_number}</p>
        <p className="draft-warning"><strong>DRAFT — REVIEW BEFORE USE</strong></p>
        <p className="muted">These source-cited fragments are read-only. They do not edit, save, or create a resume version.</p>
        <Link
          className="secondary"
          href={`/jobs/${encodeURIComponent(draft.job_id)}/resume-review?resume_version_id=${encodeURIComponent(draft.resume_version_id)}`}
        >
          Review Draft
        </Link>
      </section>
      <div className="draft-layout">
        <ResumeTailoringDraftGroup
          title="Existing Evidence to Keep"
          intro="Accepted evidence is already represented on this selected resume version."
          items={draft.keep ?? []}
          empty="No job requirements are already represented by accepted evidence on this resume version."
          selectedVersionId={draft.resume_version_id}
        />
        <ResumeTailoringDraftGroup
          title="Evidence-Backed Draft Suggestions"
          intro="Each visible draft fragment uses only its cited recorded candidate source."
          items={draft.draft_suggestions ?? []}
          empty="No evidence-backed draft fragments are available."
          selectedVersionId={draft.resume_version_id}
        />
        <ResumeTailoringDraftGroup
          title="Unsupported Requirements"
          intro="No candidate claim is generated for these requirements."
          items={draft.unsupported ?? []}
          empty="No unsupported requirements are present."
          selectedVersionId={draft.resume_version_id}
        />
        <ResumeTailoringDraftGroup
          title="Manual Review Items"
          intro="These requirements need human review before any factual statement could be considered."
          items={draft.manual_review ?? []}
          empty="No requirements need manual review."
          selectedVersionId={draft.resume_version_id}
        />
      </div>
      {draft.limitations.length > 0 && (
        <section className="auth-card dashboard-card draft-limitations">
          <h2>Draft limitations</h2>
          <ul>{draft.limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        </section>
      )}
    </>
  );
}

export function ResumeTailoringDraftLoading() {
  return <p role="status">Loading resume tailoring draft…</p>;
}

export function ResumeTailoringDraftFailure({
  retry,
  message,
}: {
  retry: () => void;
  message: string;
}) {
  return (
    <section className="auth-card dashboard-card">
      <p role="alert" className="auth-error">Could not load resume tailoring draft. {message}</p>
      <button className="secondary" onClick={retry}>Retry resume tailoring draft</button>
    </section>
  );
}

export function ResumeTailoringDraftPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [choices, setChoices] = useState<ResumeChoice[] | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(selectedVersionFromLocation);
  const [response, setResponse] = useState<DraftResponse | null>(null);
  const [choicesError, setChoicesError] = useState("");
  const [draftError, setDraftError] = useState("");
  const [choicesAttempt, setChoicesAttempt] = useState(0);
  const [draftAttempt, setDraftAttempt] = useState(0);

  useEffect(() => {
    setChoices(null);
    setChoicesError("");
    setResponse(null);
    if (!user) return;
    let active = true;
    apiClient.listResumes()
      .then(async (resumes) => {
        const versionLists = await Promise.all(
          resumes.map(async (resume) => ({
            resumeId: resume.id,
            resumeTitle: resume.title,
            versions: await apiClient.listResumeVersions(resume.id),
          })),
        );
        return versionLists.flatMap(({ resumeId, resumeTitle, versions }) =>
          versions.map((version) => ({ resumeId, resumeTitle, version })),
        );
      })
      .then((nextChoices) => {
        if (!active) return;
        setChoices(nextChoices);
        setSelectedVersionId((current) => {
          const requested = current || selectedVersionFromLocation();
          return nextChoices.some((choice) => choice.version.id === requested)
            ? requested
            : (nextChoices[0]?.version.id ?? null);
        });
      })
      .catch((reason) => {
        if (!active) return;
        setChoicesError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [choicesAttempt, refresh, user]);

  useEffect(() => {
    if (typeof window === "undefined" || choices === null) return;
    const params = new URLSearchParams(window.location.search);
    if (selectedVersionId) params.set("resume_version_id", selectedVersionId);
    else params.delete("resume_version_id");
    const query = params.toString();
    const next = window.location.pathname + (query ? `?${query}` : "");
    if (window.location.pathname + window.location.search !== next) {
      window.history.replaceState(null, "", next);
    }
  }, [choices, selectedVersionId]);

  useEffect(() => {
    setResponse(null);
    setDraftError("");
    if (
      !user ||
      choices === null ||
      !selectedVersionId ||
      !choices.some((choice) => choice.version.id === selectedVersionId)
    ) return;
    const ownerId = user.id;
    let active = true;
    apiClient.getResumeTailoringDraft(jobId, selectedVersionId)
      .then((draft) => {
        if (active) setResponse({ ownerId, jobId, resumeVersionId: selectedVersionId, draft });
      })
      .catch((reason) => {
        if (!active) return;
        setDraftError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [choices, draftAttempt, jobId, refresh, selectedVersionId, user]);

  const draft = response && response.ownerId === user?.id && response.jobId === jobId && response.resumeVersionId === selectedVersionId
    ? response.draft
    : null;
  return (
    <main className="auth-shell dashboard-shell draft-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href="/jobs">Back to jobs</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view a resume tailoring draft.</p>
            : choicesError ? <ResumeTailoringDraftFailure message={choicesError} retry={() => setChoicesAttempt((value) => value + 1)} />
              : choices === null ? <ResumeTailoringDraftLoading />
                : choices.length === 0 ? <section className="auth-card dashboard-card"><h1 className="profile-title">Resume Tailoring Draft</h1><p className="muted">Upload a resume version before viewing a draft.</p><Link className="secondary" href="/resumes">Manage resumes</Link></section>
                  : <>
                    <section className="auth-card dashboard-card draft-selector">
                      <label htmlFor="resume-version-select">Choose a resume version</label>
                      <select
                        id="resume-version-select"
                        value={selectedVersionId ?? ""}
                        onChange={(event) => setSelectedVersionId(event.target.value || null)}
                      >
                        {choices.map((choice) => <option key={choice.version.id} value={choice.version.id}>{choice.resumeTitle} — version {choice.version.version_number}</option>)}
                      </select>
                    </section>
                    {draft ? <ResumeTailoringDraftContent draft={draft} />
                      : draftError ? <ResumeTailoringDraftFailure message={draftError} retry={() => setDraftAttempt((value) => value + 1)} />
                        : <ResumeTailoringDraftLoading />}
                  </>}
    </main>
  );
}
