"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type ResumeVersion,
  type SkillGapAnalysis,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type GapRequirement = NonNullable<SkillGapAnalysis["covered"]>[number];
type CandidateSource = NonNullable<GapRequirement["sources"]>[number];
type ResumeChoice = { resumeId: string; resumeTitle: string; version: ResumeVersion };
type SkillGapResponse = {
  ownerId: string;
  jobId: string;
  resumeVersionId: string;
  analysis: SkillGapAnalysis;
};

function selectedVersionFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const values = new URLSearchParams(window.location.search).getAll("resume_version_id");
  return values.length === 1 && values[0] ? values[0] : null;
}

function sourceLabel(source: CandidateSource, selectedVersionId: string): string {
  if (source.source_type === "CONFIRMED_BY_USER") {
    return "Confirmed by you — recorded candidate evidence, not evidence on this resume.";
  }
  if (source.source_type === "RESUME_EVIDENCE") {
    const resume = source.resume_title || "resume";
    const version = source.resume_version_number === null || source.resume_version_number === undefined
      ? "" : `, version ${source.resume_version_number}`;
    const ordinal = source.evidence_ordinal === null || source.evidence_ordinal === undefined
      ? "" : `, evidence item ${source.evidence_ordinal}`;
    const selected = source.resume_version_id === selectedVersionId;
    return `${resume}${version}${ordinal} — parser-recognized resume evidence${selected
      ? " shown on the selected resume version."
      : " on another resume version; it is not shown on the selected version."}`;
  }
  return `${source.project_title || "Project"} — project technology recorded by you, not shown in this resume.`;
}

export function SkillGapRequirement({
  requirement,
  selectedVersionId,
}: {
  requirement: GapRequirement;
  selectedVersionId: string;
}) {
  const sources = requirement.sources ?? [];
  return (
    <article className="gap-requirement">
      <header>
        <h3>{requirement.name}</h3>
        <p className="muted">{requirement.category}{requirement.importance ? ` · ${requirement.importance}` : ""}</p>
      </header>
      {requirement.description && <p className="gap-description">{requirement.description}</p>}
      <p><strong>Why this is listed:</strong> {requirement.explanation}</p>
      <p><strong>Limitation:</strong> {requirement.limitation}</p>
      {sources.length ? (
        <>
          <h4>Recorded sources</h4>
          <ul className="gap-sources">
            {sources.map((source) => (
              <li key={`${source.source_type}-${source.source_id}`}>
                {sourceLabel(source, selectedVersionId)}
              </li>
            ))}
          </ul>
        </>
      ) : <p className="muted">No recorded sources.</p>}
    </article>
  );
}

function SkillGapGroup({
  title,
  intro,
  requirements,
  empty,
  selectedVersionId,
}: {
  title: string;
  intro: string;
  requirements: GapRequirement[];
  empty: string;
  selectedVersionId: string;
}) {
  return (
    <section className="auth-card dashboard-card gap-group">
      <h2>{title}</h2>
      <p className="muted">{intro}</p>
      {requirements.length ? requirements.map((requirement) => (
        <SkillGapRequirement
          key={`${requirement.category}-${requirement.requirement_id}`}
          requirement={requirement}
          selectedVersionId={selectedVersionId}
        />
      )) : <p className="muted">{empty}</p>}
    </section>
  );
}

export function SkillGapContent({ analysis }: { analysis: SkillGapAnalysis }) {
  return (
    <>
      <section className="auth-card dashboard-card gap-introduction">
        <h1 className="profile-title">Skill gap analysis</h1>
        <p className="fit-job">{analysis.job_title}{analysis.company_name ? ` · ${analysis.company_name}` : ""}</p>
        <p className="gap-version"><strong>Selected resume:</strong> {analysis.resume_title}, version {analysis.resume_version_number}</p>
        <p className="muted">This view groups explicit job requirements by recorded evidence. It does not assess ability, predict hiring outcomes, or recommend changes.</p>
      </section>
      <div className="gap-layout">
        <SkillGapGroup
          title="Covered"
          intro="Accepted exact catalog-skill evidence is shown on the selected resume version."
          requirements={analysis.covered ?? []}
          empty="No job requirements are covered by accepted evidence on this resume version."
          selectedVersionId={analysis.resume_version_id}
        />
        <SkillGapGroup
          title="Resume presentation gaps"
          intro="Recorded candidate evidence exists, but it is not shown on this resume."
          requirements={analysis.resume_presentation_gaps ?? []}
          empty="No requirements are in this group."
          selectedVersionId={analysis.resume_version_id}
        />
        <SkillGapGroup
          title="Candidate evidence gaps"
          intro="No recorded supporting evidence."
          requirements={analysis.candidate_evidence_gaps ?? []}
          empty="No requirements are in this group."
          selectedVersionId={analysis.resume_version_id}
        />
        <SkillGapGroup
          title="Unknown / unassessed"
          intro="Education and eligibility requirements are shown here because the available records do not support a deterministic evaluation."
          requirements={analysis.unknown ?? []}
          empty="No requirements are unknown or unassessed."
          selectedVersionId={analysis.resume_version_id}
        />
      </div>
      {analysis.limitations.length > 0 && (
        <section className="auth-card dashboard-card gap-limitations">
          <h2>Analysis limitations</h2>
          <ul>{analysis.limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        </section>
      )}
    </>
  );
}

export function SkillGapLoading() { return <p role="status">Loading skill gap analysis…</p>; }

export function SkillGapFailure({ retry, message }: { retry: () => void; message: string }) {
  return <section className="auth-card dashboard-card"><p role="alert" className="auth-error">Could not load skill gap analysis. {message}</p><button className="secondary" onClick={retry}>Retry skill gap analysis</button></section>;
}

export function SkillGapPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [choices, setChoices] = useState<ResumeChoice[] | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(selectedVersionFromLocation);
  const [response, setResponse] = useState<SkillGapResponse | null>(null);
  const [choicesError, setChoicesError] = useState("");
  const [analysisError, setAnalysisError] = useState("");
  const [choicesAttempt, setChoicesAttempt] = useState(0);
  const [analysisAttempt, setAnalysisAttempt] = useState(0);

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
    setAnalysisError("");
    if (
      !user ||
      choices === null ||
      !selectedVersionId ||
      !choices.some((choice) => choice.version.id === selectedVersionId)
    ) return;
    const ownerId = user.id;
    let active = true;
    apiClient.getJobSkillGaps(jobId, selectedVersionId)
      .then((analysis) => {
        if (active) setResponse({ ownerId, jobId, resumeVersionId: selectedVersionId, analysis });
      })
      .catch((reason) => {
        if (!active) return;
        setAnalysisError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [analysisAttempt, choices, jobId, refresh, selectedVersionId, user]);

  const analysis = response && response.ownerId === user?.id && response.jobId === jobId && response.resumeVersionId === selectedVersionId
    ? response.analysis
    : null;
  return (
    <main className="auth-shell dashboard-shell gap-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href="/jobs">Back to jobs</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view skill gap analysis.</p>
            : choicesError ? <SkillGapFailure message={choicesError} retry={() => setChoicesAttempt((value) => value + 1)} />
              : choices === null ? <SkillGapLoading />
                : choices.length === 0 ? <section className="auth-card dashboard-card"><h1 className="profile-title">Skill gap analysis</h1><p className="muted">Upload a resume version before viewing skill gaps.</p><Link className="secondary" href="/resumes">Manage resumes</Link></section>
                  : <>
                    <section className="auth-card dashboard-card gap-selector">
                      <label htmlFor="resume-version-select">Choose a resume version</label>
                      <select
                        id="resume-version-select"
                        value={selectedVersionId ?? ""}
                        onChange={(event) => setSelectedVersionId(event.target.value || null)}
                      >
                        {choices.map((choice) => <option key={choice.version.id} value={choice.version.id}>{choice.resumeTitle} — version {choice.version.version_number}</option>)}
                      </select>
                    </section>
                    {analysis ? <SkillGapContent analysis={analysis} />
                      : analysisError ? <SkillGapFailure message={analysisError} retry={() => setAnalysisAttempt((value) => value + 1)} />
                        : <SkillGapLoading />}
                  </>}
    </main>
  );
}
