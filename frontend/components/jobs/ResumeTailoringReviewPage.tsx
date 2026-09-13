"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type ResumeTailoringReview,
  type ResumeTailoringReviewItemUpdate,
  type ResumeVersion,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type ReviewItem = NonNullable<ResumeTailoringReview["items"]>[number];
type CandidateSource = NonNullable<ReviewItem["provenance"]>[number];
type ResumeChoice = { resumeId: string; resumeTitle: string; version: ResumeVersion };

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
      : " is outside the selected resume version."}`;
  }
  return `${source.project_title || "Project"} — recorded project technology source.`;
}

function ReviewItemCard({
  item,
  selectedVersionId,
  finalized,
  busy,
  onUpdate,
}: {
  item: ReviewItem;
  selectedVersionId: string;
  finalized: boolean;
  busy: boolean;
  onUpdate: (payload: ResumeTailoringReviewItemUpdate) => void;
}) {
  const [wording, setWording] = useState(item.user_edited_text ?? "");

  useEffect(() => {
    setWording(item.user_edited_text ?? "");
  }, [item.id, item.user_edited_text]);

  const canSaveWording = Boolean(wording.trim());
  return (
    <article className="review-item">
      <header>
        <div>
          <h3>{item.name}</h3>
          <p className="muted">{item.category}{item.importance ? ` · ${item.importance}` : ""}</p>
        </div>
        <p className={`review-decision review-decision-${item.decision.toLowerCase()}`}><strong>{item.decision}</strong></p>
      </header>
      {item.description && <p className="review-description">{item.description}</p>}
      <p><strong>System draft</strong></p>
      <p className="review-system-draft">{item.original_draft_text}</p>
      <p><strong>Why this draft exists:</strong> {item.reason}</p>
      <p><strong>Safety boundary:</strong> {item.limitation}</p>
      <h4>Provenance</h4>
      <ul className="review-provenance">
        {(item.provenance ?? []).map((source) => (
          <li key={`${source.source_type}-${source.source_id}`}>{sourceLabel(source, selectedVersionId)}</li>
        ))}
      </ul>
      {item.user_edited_text && (
        <section className="review-user-edited">
          <h4>USER EDITED</h4>
          <p>{item.user_edited_text}</p>
          <p className="muted">This is your chosen wording only. It is not candidate evidence.</p>
        </section>
      )}
      {finalized ? (
        <p className="review-read-only"><strong>Read-only:</strong> this review is finalized.</p>
      ) : (
        <section className="review-controls" aria-label={`Review controls for ${item.name}`}>
          <div className="form-actions">
            <button type="button" disabled={busy} onClick={() => onUpdate({ decision: "ACCEPTED" })}>ACCEPT</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => onUpdate({ decision: "REJECTED" })}>REJECT</button>
          </div>
          <label htmlFor={`review-wording-${item.id}`}>Optional user wording</label>
          <textarea
            id={`review-wording-${item.id}`}
            value={wording}
            disabled={busy}
            maxLength={1000}
            onChange={(event) => setWording(event.target.value)}
          />
          <div className="form-actions">
            <button type="button" className="secondary" disabled={busy || !canSaveWording} onClick={() => onUpdate({ user_edited_text: wording })}>
              Save user edit
            </button>
            {item.user_edited_text && (
              <button type="button" className="secondary" disabled={busy} onClick={() => onUpdate({ user_edited_text: null })}>
                Clear user edit
              </button>
            )}
          </div>
        </section>
      )}
    </article>
  );
}

export function ResumeTailoringReviewContent({
  review,
  busy,
  onUpdate,
  onFinalize,
}: {
  review: ResumeTailoringReview;
  busy: boolean;
  onUpdate: (itemId: string, payload: ResumeTailoringReviewItemUpdate) => void;
  onFinalize: () => void;
}) {
  const [confirmingFinalization, setConfirmingFinalization] = useState(false);
  const items = review.items ?? [];
  const finalized = review.status === "FINALIZED";
  const pending = items.filter((item) => item.decision === "PENDING").length;
  return (
    <>
      <section className="auth-card dashboard-card review-introduction">
        <h1 className="profile-title">Resume Draft Review</h1>
        <p className="fit-job">{review.job_title}{review.company_name ? ` · ${review.company_name}` : ""}</p>
        <p className="review-version"><strong>Selected resume:</strong> {review.resume_title}, version {review.resume_version_number}</p>
        <p className={finalized ? "review-status review-finalized-status" : "review-status"}>
          <strong>Review status:</strong> {review.status}
        </p>
        <p className="muted">System drafts and their provenance are preserved. Your edited wording remains separate from candidate evidence.</p>
      </section>
      <section className="auth-card dashboard-card review-items">
        <h2>Reviewable draft suggestions</h2>
        {items.length ? items.map((item) => (
          <ReviewItemCard
            key={item.id}
            item={item}
            selectedVersionId={review.source_resume_version_id}
            finalized={finalized}
            busy={busy}
            onUpdate={(payload) => onUpdate(item.id, payload)}
          />
        )) : <p className="muted">This Phase 16 draft had no evidence-backed suggestions to review.</p>}
      </section>
      {finalized ? (
        <section className="auth-card dashboard-card review-finalized">
          <h2>Review finalized</h2>
          <p>This review is read-only. It did not create a ResumeVersion or change candidate evidence.</p>
        </section>
      ) : confirmingFinalization ? (
        <section className="auth-card dashboard-card review-finalization-confirmation">
          <h2>Confirm finalization</h2>
          <p>Finalizing makes this review read-only. It does not generate a document or create a ResumeVersion.</p>
          <div className="form-actions">
            <button type="button" disabled={busy} onClick={onFinalize}>Confirm finalization</button>
            <button type="button" className="secondary" disabled={busy} onClick={() => setConfirmingFinalization(false)}>Cancel</button>
          </div>
        </section>
      ) : (
        <section className="auth-card dashboard-card review-finalization">
          <h2>Finalize review</h2>
          <p className="muted">{pending ? `${pending} suggestion${pending === 1 ? "" : "s"} still need${pending === 1 ? "s" : ""} ACCEPT or REJECT.` : "All suggestions have a recorded decision."}</p>
          <button type="button" disabled={busy || pending > 0} onClick={() => setConfirmingFinalization(true)}>Finalize review</button>
        </section>
      )}
    </>
  );
}

export function ResumeTailoringReviewPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [choices, setChoices] = useState<ResumeChoice[] | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(selectedVersionFromLocation);
  const [review, setReview] = useState<ResumeTailoringReview | null>(null);
  const [reviewMissing, setReviewMissing] = useState(false);
  const [choicesError, setChoicesError] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [choicesAttempt, setChoicesAttempt] = useState(0);
  const [reviewAttempt, setReviewAttempt] = useState(0);
  const [busy, setBusy] = useState(false);

  function handleError(reason: unknown, setter: (message: string) => void) {
    setter(authErrorMessage(reason));
    if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
  }

  useEffect(() => {
    setChoices(null);
    setChoicesError("");
    if (!user) return;
    let active = true;
    apiClient.listResumes()
      .then(async (resumes) => {
        const versions = await Promise.all(resumes.map(async (resume) => ({
          resume,
          versions: await apiClient.listResumeVersions(resume.id),
        })));
        if (!active) return;
        setChoices(versions.flatMap(({ resume, versions: versionList }) => versionList.map((version) => ({
          resumeId: resume.id,
          resumeTitle: resume.title,
          version,
        }))));
      })
      .catch((reason) => {
        if (active) handleError(reason, setChoicesError);
      });
    return () => { active = false; };
  }, [choicesAttempt, refresh, user]);

  useEffect(() => {
    if (!choices?.length) return;
    setSelectedVersionId((current) => choices.some((choice) => choice.version.id === current)
      ? current : choices[0].version.id);
  }, [choices]);

  useEffect(() => {
    if (typeof window === "undefined" || !selectedVersionId) return;
    const url = new URL(window.location.href);
    url.searchParams.set("resume_version_id", selectedVersionId);
    window.history.replaceState(null, "", url.pathname + url.search);
  }, [selectedVersionId]);

  useEffect(() => {
    setReview(null);
    setReviewMissing(false);
    setReviewError("");
    if (!user || !selectedVersionId) return;
    let active = true;
    apiClient.getResumeTailoringReview(jobId, selectedVersionId)
      .then((data) => { if (active) setReview(data); })
      .catch((reason) => {
        if (!active) return;
        if (reason instanceof ApiError && reason.status === 404) {
          setReviewMissing(true);
          return;
        }
        handleError(reason, setReviewError);
      });
    return () => { active = false; };
  }, [jobId, refresh, reviewAttempt, selectedVersionId, user]);

  async function createReview() {
    if (!selectedVersionId) return;
    setBusy(true);
    setReviewError("");
    try {
      setReview(await apiClient.createResumeTailoringReview(jobId, { resume_version_id: selectedVersionId }));
      setReviewMissing(false);
    } catch (reason) {
      handleError(reason, setReviewError);
    } finally {
      setBusy(false);
    }
  }

  async function updateItem(itemId: string, payload: ResumeTailoringReviewItemUpdate) {
    if (!review) return;
    setBusy(true);
    setReviewError("");
    try {
      setReview(await apiClient.updateResumeTailoringReviewItem(jobId, review.id, itemId, payload));
    } catch (reason) {
      handleError(reason, setReviewError);
    } finally {
      setBusy(false);
    }
  }

  async function finalizeReview() {
    if (!review) return;
    setBusy(true);
    setReviewError("");
    try {
      setReview(await apiClient.finalizeResumeTailoringReview(jobId, review.id));
    } catch (reason) {
      handleError(reason, setReviewError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell dashboard-shell review-shell">
      <Link href="/jobs" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href={`/jobs/${encodeURIComponent(jobId)}/resume-draft`}>Back to Resume Tailoring</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to review a resume draft.</p>
            : choicesError ? <section className="auth-card dashboard-card"><p role="alert" className="auth-error">Could not load resume versions. {choicesError}</p><button className="secondary" onClick={() => setChoicesAttempt((value) => value + 1)}>Retry resume versions</button></section>
              : choices === null ? <p role="status">Loading resume versions…</p>
                : choices.length === 0 ? <section className="auth-card dashboard-card"><h1 className="profile-title">Resume Draft Review</h1><p className="muted">Upload a resume version before reviewing a draft.</p><Link className="secondary" href="/resumes">Manage resumes</Link></section>
                  : <>
                    <section className="auth-card dashboard-card review-selector">
                      <label htmlFor="review-resume-version-select">Choose a resume version</label>
                      <select id="review-resume-version-select" value={selectedVersionId ?? ""} onChange={(event) => setSelectedVersionId(event.target.value || null)}>
                        {choices.map((choice) => <option key={choice.version.id} value={choice.version.id}>{choice.resumeTitle} — version {choice.version.version_number}</option>)}
                      </select>
                    </section>
                    {reviewError && <section className="auth-card dashboard-card"><p role="alert" className="auth-error">{reviewError}</p><button className="secondary" disabled={busy} onClick={() => setReviewAttempt((value) => value + 1)}>Reload review</button></section>}
                    {review ? <ResumeTailoringReviewContent review={review} busy={busy} onUpdate={updateItem} onFinalize={finalizeReview} />
                      : reviewMissing ? <section className="auth-card dashboard-card review-start"><h1 className="profile-title">Resume Draft Review</h1><p>This creates a saved snapshot of the current evidence-backed Phase 16 suggestions for the selected resume version.</p><p className="muted">It does not create a ResumeVersion or change candidate evidence.</p><button type="button" disabled={busy} onClick={() => void createReview()}>Start review</button></section>
                        : !reviewError && <p role="status">Loading saved review…</p>}
                  </>}
    </main>
  );
}
