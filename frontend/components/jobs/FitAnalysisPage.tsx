"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ApiError, apiClient, authErrorMessage, type FitAnalysis } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type FitResponse = { ownerId: string; jobId: string; analysis: FitAnalysis };
type FitRequirementRead = NonNullable<FitAnalysis["matched"]>[number];
type CandidateSource = NonNullable<FitRequirementRead["sources"]>[number];

function sourceLabel(source: CandidateSource): string {
  if (source.source_type === "CONFIRMED_BY_USER") {
    return "Confirmed by you — this records your selection; it does not verify proficiency.";
  }
  if (source.source_type === "RESUME_EVIDENCE") {
    const resume = source.resume_title || "resume";
    const version = source.resume_version_number === null || source.resume_version_number === undefined
      ? "" : `, version ${source.resume_version_number}`;
    const ordinal = source.evidence_ordinal === null || source.evidence_ordinal === undefined
      ? "" : `, evidence item ${source.evidence_ordinal}`;
    return `${resume}${version}${ordinal} — parser-recognized resume evidence; it may be from a historical version and is not verified proficiency.`;
  }
  return `${source.project_title || "Project"} — project usage recorded by you; it does not verify proficiency.`;
}

export function FitRequirement({ requirement }: { requirement: FitRequirementRead }) {
  return (
    <article className="fit-requirement">
      <header>
        <div>
          <h3>{requirement.name}</h3>
          <p className="muted">{requirement.category}{requirement.importance ? ` · ${requirement.importance}` : ""}</p>
        </div>
      </header>
      {requirement.description && <p className="fit-description">{requirement.description}</p>}
      <p><strong>Why this is listed:</strong> {requirement.explanation}</p>
      <p><strong>Limitation:</strong> {requirement.limitation}</p>
      <h4>Recorded sources</h4>
      <ul className="fit-sources">
        {(requirement.sources ?? []).map((source) => <li key={`${source.source_type}-${source.source_id}`}>{sourceLabel(source)}</li>)}
      </ul>
      {(requirement.sources ?? []).length === 0 && <p className="muted">No recorded sources.</p>}
    </article>
  );
}

function RequirementGroup({
  title,
  intro,
  requirements,
  empty,
}: {
  title: string;
  intro: string;
  requirements: FitRequirementRead[];
  empty: string;
}) {
  return (
    <section className="auth-card dashboard-card fit-group">
      <h2>{title}</h2>
      <p className="muted">{intro}</p>
      {requirements.length ? requirements.map((requirement) => (
        <FitRequirement key={`${requirement.category}-${requirement.requirement_id}`} requirement={requirement} />
      )) : <p className="muted">{empty}</p>}
    </section>
  );
}

export function FitAnalysisContent({ analysis }: { analysis: FitAnalysis }) {
  return (
    <>
      <section className="auth-card dashboard-card fit-introduction">
        <h1 className="profile-title">Fit analysis</h1>
        <p className="fit-job">{analysis.job_title}{analysis.company_name ? ` · ${analysis.company_name}` : ""}</p>
        <p className="muted">This view compares stated job requirements with recorded candidate information. It does not assess ability, predict hiring outcomes, or make a recommendation.</p>
      </section>
      <div className="fit-layout">
        <RequirementGroup
          title="Recorded evidence"
          intro="These requirements have linked candidate records. Read each source and limitation before drawing conclusions."
          requirements={analysis.matched ?? []}
          empty="No job requirements have recorded candidate evidence."
        />
        <RequirementGroup
          title="No recorded evidence"
          intro="No linked candidate record was found for these requirements. This does not mean you lack the capability."
          requirements={analysis.missing ?? []}
          empty="No requirements are in this group."
        />
        <RequirementGroup
          title="Unknown"
          intro="The available records do not support a determination for these education or eligibility requirements."
          requirements={analysis.unknown ?? []}
          empty="No requirements are unknown."
        />
      </div>
      {analysis.limitations.length > 0 && (
        <section className="auth-card dashboard-card fit-limitations">
          <h2>Analysis limitations</h2>
          <ul>{analysis.limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        </section>
      )}
    </>
  );
}

export function FitAnalysisLoading() { return <p role="status">Loading fit analysis…</p>; }

export function FitAnalysisFailure({ retry, message }: { retry: () => void; message: string }) {
  return <section className="auth-card dashboard-card"><p role="alert" className="auth-error">Could not load fit analysis. {message}</p><button className="secondary" onClick={retry}>Retry fit analysis</button></section>;
}

export function FitAnalysisPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [response, setResponse] = useState<FitResponse | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    setResponse(null);
    setError("");
    if (!user) return;
    const ownerId = user.id;
    let active = true;
    apiClient.getJobFit(jobId)
      .then((analysis) => {
        if (active) setResponse({ ownerId, jobId, analysis });
      })
      .catch((reason) => {
        if (!active) return;
        setError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [attempt, jobId, refresh, user]);

  const analysis = response && response.ownerId === user?.id && response.jobId === jobId ? response.analysis : null;
  return (
    <main className="auth-shell dashboard-shell fit-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href="/jobs">Back to jobs</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view a fit analysis.</p>
            : analysis ? <FitAnalysisContent analysis={analysis} />
              : error ? <FitAnalysisFailure message={error} retry={() => setAttempt((value) => value + 1)} />
                : <FitAnalysisLoading />}
    </main>
  );
}
