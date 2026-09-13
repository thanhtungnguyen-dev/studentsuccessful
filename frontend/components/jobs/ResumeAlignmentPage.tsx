"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type ResumeAlignment,
  type ResumeVersion,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type AlignmentRequirement = NonNullable<ResumeAlignment["shown_on_resume"]>[number];
type CandidateSource = NonNullable<AlignmentRequirement["sources"]>[number];
type ResumeChoice = { resumeId: string; resumeTitle: string; version: ResumeVersion };
type AlignmentResponse = {
  ownerId: string;
  jobId: string;
  resumeVersionId: string;
  alignment: ResumeAlignment;
};

function selectedVersionFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const values = new URLSearchParams(window.location.search).getAll("resume_version_id");
  return values.length === 1 && values[0] ? values[0] : null;
}

function sourceLabel(source: CandidateSource): string {
  if (source.source_type === "CONFIRMED_BY_USER") {
    return "Confirmed by you — recorded candidate evidence, not evidence on this resume version.";
  }
  if (source.source_type === "RESUME_EVIDENCE") {
    const resume = source.resume_title || "resume";
    const version = source.resume_version_number === null || source.resume_version_number === undefined
      ? "" : `, version ${source.resume_version_number}`;
    const ordinal = source.evidence_ordinal === null || source.evidence_ordinal === undefined
      ? "" : `, evidence item ${source.evidence_ordinal}`;
    return `${resume}${version}${ordinal} — parser-recognized evidence on the selected resume version.`;
  }
  return `${source.project_title || "Project"} — project technology recorded by you, not shown in this resume version.`;
}

export function ResumeAlignmentRequirement({ requirement }: { requirement: AlignmentRequirement }) {
  const sources = requirement.sources ?? [];
  return (
    <article className="alignment-requirement">
      <header>
        <h3>{requirement.name}</h3>
        <p className="muted">{requirement.category}{requirement.importance ? ` · ${requirement.importance}` : ""}</p>
      </header>
      {requirement.description && <p className="alignment-description">{requirement.description}</p>}
      <p><strong>Why this is listed:</strong> {requirement.explanation}</p>
      <p><strong>Limitation:</strong> {requirement.limitation}</p>
      {sources.length ? (
        <>
          <h4>Recorded sources</h4>
          <ul className="alignment-sources">
            {sources.map((source) => <li key={`${source.source_type}-${source.source_id}`}>{sourceLabel(source)}</li>)}
          </ul>
        </>
      ) : <p className="muted">No recorded sources.</p>}
    </article>
  );
}

function AlignmentGroup({
  title,
  intro,
  requirements,
  empty,
}: {
  title: string;
  intro: string;
  requirements: AlignmentRequirement[];
  empty: string;
}) {
  return (
    <section className="auth-card dashboard-card alignment-group">
      <h2>{title}</h2>
      <p className="muted">{intro}</p>
      {requirements.length ? requirements.map((requirement) => (
        <ResumeAlignmentRequirement
          key={`${requirement.category}-${requirement.requirement_id}`}
          requirement={requirement}
        />
      )) : <p className="muted">{empty}</p>}
    </section>
  );
}

export function ResumeAlignmentContent({ alignment }: { alignment: ResumeAlignment }) {
  return (
    <>
      <section className="auth-card dashboard-card alignment-introduction">
        <h1 className="profile-title">Resume alignment</h1>
        <p className="fit-job">{alignment.job_title}{alignment.company_name ? ` · ${alignment.company_name}` : ""}</p>
        <p className="alignment-version"><strong>Selected resume:</strong> {alignment.resume_title}, version {alignment.resume_version_number}</p>
        <p className="muted">This view compares one resume version with explicit job requirements. It records where evidence appears; it does not assess ability, predict hiring outcomes, or recommend claims to add.</p>
      </section>
      <div className="alignment-layout">
        <AlignmentGroup
          title="Shown on this resume"
          intro="These exact catalog-skill requirements have accepted evidence on the selected resume version."
          requirements={alignment.shown_on_resume ?? []}
          empty="No job requirements have accepted evidence on this resume version."
        />
        <AlignmentGroup
          title="Candidate evidence not shown"
          intro="Recorded candidate evidence exists, but it is not shown in this resume version."
          requirements={alignment.candidate_evidence_not_shown ?? []}
          empty="No requirements are in this group."
        />
        <AlignmentGroup
          title="No recorded evidence"
          intro="No accepted selected-resume, confirmed-skill, or project-technology source was found. This does not mean you lack the capability."
          requirements={alignment.no_recorded_evidence ?? []}
          empty="No requirements are in this group."
        />
        <AlignmentGroup
          title="Unknown / unassessed"
          intro="Education and eligibility requirements are shown here because the available records do not support a deterministic evaluation."
          requirements={alignment.unknown_unassessed ?? []}
          empty="No requirements are unknown or unassessed."
        />
      </div>
      {alignment.limitations.length > 0 && (
        <section className="auth-card dashboard-card alignment-limitations">
          <h2>Alignment limitations</h2>
          <ul>{alignment.limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        </section>
      )}
    </>
  );
}

export function ResumeAlignmentLoading() { return <p role="status">Loading resume alignment…</p>; }

export function ResumeAlignmentFailure({ retry, message }: { retry: () => void; message: string }) {
  return <section className="auth-card dashboard-card"><p role="alert" className="auth-error">Could not load resume alignment. {message}</p><button className="secondary" onClick={retry}>Retry resume alignment</button></section>;
}

export function ResumeAlignmentPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [choices, setChoices] = useState<ResumeChoice[] | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(selectedVersionFromLocation);
  const [response, setResponse] = useState<AlignmentResponse | null>(null);
  const [choicesError, setChoicesError] = useState("");
  const [alignmentError, setAlignmentError] = useState("");
  const [choicesAttempt, setChoicesAttempt] = useState(0);
  const [alignmentAttempt, setAlignmentAttempt] = useState(0);

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
    setAlignmentError("");
    if (
      !user ||
      choices === null ||
      !selectedVersionId ||
      !choices.some((choice) => choice.version.id === selectedVersionId)
    ) return;
    const ownerId = user.id;
    let active = true;
    apiClient.getJobResumeAlignment(jobId, selectedVersionId)
      .then((alignment) => {
        if (active) setResponse({ ownerId, jobId, resumeVersionId: selectedVersionId, alignment });
      })
      .catch((reason) => {
        if (!active) return;
        setAlignmentError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [alignmentAttempt, choices, jobId, refresh, selectedVersionId, user]);

  const alignment = response && response.ownerId === user?.id && response.jobId === jobId && response.resumeVersionId === selectedVersionId
    ? response.alignment
    : null;
  return (
    <main className="auth-shell dashboard-shell alignment-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href="/jobs">Back to jobs</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view resume alignment.</p>
            : choicesError ? <ResumeAlignmentFailure message={choicesError} retry={() => setChoicesAttempt((value) => value + 1)} />
              : choices === null ? <ResumeAlignmentLoading />
                : choices.length === 0 ? <section className="auth-card dashboard-card"><h1 className="profile-title">Resume alignment</h1><p className="muted">Upload a resume version before viewing alignment.</p><Link className="secondary" href="/resumes">Manage resumes</Link></section>
                  : <>
                    <section className="auth-card dashboard-card alignment-selector">
                      <label htmlFor="resume-version-select">Choose a resume version</label>
                      <select
                        id="resume-version-select"
                        value={selectedVersionId ?? ""}
                        onChange={(event) => setSelectedVersionId(event.target.value || null)}
                      >
                        {choices.map((choice) => <option key={choice.version.id} value={choice.version.id}>{choice.resumeTitle} — version {choice.version.version_number}</option>)}
                      </select>
                    </section>
                    {alignment ? <ResumeAlignmentContent alignment={alignment} />
                      : alignmentError ? <ResumeAlignmentFailure message={alignmentError} retry={() => setAlignmentAttempt((value) => value + 1)} />
                        : <ResumeAlignmentLoading />}
                  </>}
    </main>
  );
}
