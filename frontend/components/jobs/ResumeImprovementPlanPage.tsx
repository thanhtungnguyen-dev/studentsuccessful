"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  ApiError,
  apiClient,
  authErrorMessage,
  type ResumeImprovementPlan,
  type ResumeVersion,
} from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type PlanAction = NonNullable<ResumeImprovementPlan["keep"]>[number];
type CandidateSource = NonNullable<PlanAction["sources"]>[number];
type ResumeChoice = { resumeId: string; resumeTitle: string; version: ResumeVersion };
type PlanResponse = {
  ownerId: string;
  jobId: string;
  resumeVersionId: string;
  plan: ResumeImprovementPlan;
};

function selectedVersionFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const values = new URLSearchParams(window.location.search).getAll("resume_version_id");
  return values.length === 1 && values[0] ? values[0] : null;
}

function sourceLabel(source: CandidateSource, selectedVersionId: string): string {
  if (source.source_type === "CONFIRMED_BY_USER") {
    return "Confirmed by you — recorded candidate evidence, not represented on this resume version.";
  }
  if (source.source_type === "RESUME_EVIDENCE") {
    const resume = source.resume_title || "resume";
    const version = source.resume_version_number === null || source.resume_version_number === undefined
      ? "" : `, version ${source.resume_version_number}`;
    const ordinal = source.evidence_ordinal === null || source.evidence_ordinal === undefined
      ? "" : `, evidence item ${source.evidence_ordinal}`;
    const selected = source.resume_version_id === selectedVersionId;
    return `${resume}${version}${ordinal} — parser-recognized resume evidence${selected
      ? " already shown on the selected resume version."
      : " on another resume version; it is not shown on the selected version."}`;
  }
  return `${source.project_title || "Project"} — project technology recorded by you, not represented on this resume.`;
}

export function ResumePlanAction({
  action,
  selectedVersionId,
}: {
  action: PlanAction;
  selectedVersionId: string;
}) {
  const sources = action.sources ?? [];
  return (
    <article className="plan-action">
      <header>
        <h3>{action.name}</h3>
        <p className="muted">{action.category}{action.importance ? ` · ${action.importance}` : ""}</p>
      </header>
      {action.description && <p className="plan-description">{action.description}</p>}
      <p className="muted"><strong>Action:</strong> {action.action}</p>
      <p><strong>Reason:</strong> {action.reason}</p>
      <p><strong>Limitation:</strong> {action.limitation}</p>
      {sources.length ? (
        <>
          <h4>Recorded sources</h4>
          <ul className="plan-sources">
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

function ResumePlanGroup({
  title,
  intro,
  actions,
  empty,
  selectedVersionId,
}: {
  title: string;
  intro: string;
  actions: PlanAction[];
  empty: string;
  selectedVersionId: string;
}) {
  return (
    <section className="auth-card dashboard-card plan-group">
      <h2>{title}</h2>
      <p className="muted">{intro}</p>
      {actions.length ? actions.map((action) => (
        <ResumePlanAction
          key={`${action.category}-${action.requirement_id}`}
          action={action}
          selectedVersionId={selectedVersionId}
        />
      )) : <p className="muted">{empty}</p>}
    </section>
  );
}

export function ResumeImprovementPlanContent({ plan }: { plan: ResumeImprovementPlan }) {
  return (
    <>
      <section className="auth-card dashboard-card plan-introduction">
        <h1 className="profile-title">Resume Improvement Plan</h1>
        <p className="fit-job">{plan.job_title}{plan.company_name ? ` · ${plan.company_name}` : ""}</p>
        <p className="plan-version"><strong>Selected resume:</strong> {plan.resume_title}, version {plan.resume_version_number}</p>
        <p className="muted">This plan lists conservative actions based only on recorded evidence. It does not generate resume text, assess ability, or predict hiring outcomes.</p>
      </section>
      <div className="plan-layout">
        <ResumePlanGroup
          title="Already represented"
          intro="Accepted evidence is already shown on this selected resume version. No change is required."
          actions={plan.keep ?? []}
          empty="No job requirements are already represented by accepted evidence on this resume version."
          selectedVersionId={plan.resume_version_id}
        />
        <ResumePlanGroup
          title="Existing evidence you may want to surface"
          intro="Recorded candidate evidence exists but is not shown on this resume version."
          actions={plan.consider_adding_existing_evidence ?? []}
          empty="No requirements are in this group."
          selectedVersionId={plan.resume_version_id}
        />
        <ResumePlanGroup
          title="Do not claim without evidence"
          intro="No recorded supporting evidence supports adding these requirements to this resume."
          actions={plan.do_not_claim_without_evidence ?? []}
          empty="No requirements are in this group."
          selectedVersionId={plan.resume_version_id}
        />
        <ResumePlanGroup
          title="Needs manual review"
          intro="These requirements cannot be evaluated safely with existing deterministic evidence."
          actions={plan.manual_review ?? []}
          empty="No requirements need manual review."
          selectedVersionId={plan.resume_version_id}
        />
      </div>
      {plan.limitations.length > 0 && (
        <section className="auth-card dashboard-card plan-limitations">
          <h2>Plan limitations</h2>
          <ul>{plan.limitations.map((limitation, index) => <li key={`${limitation}-${index}`}>{limitation}</li>)}</ul>
        </section>
      )}
    </>
  );
}

export function ResumeImprovementPlanLoading() { return <p role="status">Loading resume improvement plan…</p>; }

export function ResumeImprovementPlanFailure({ retry, message }: { retry: () => void; message: string }) {
  return <section className="auth-card dashboard-card"><p role="alert" className="auth-error">Could not load resume improvement plan. {message}</p><button className="secondary" onClick={retry}>Retry resume improvement plan</button></section>;
}

export function ResumeImprovementPlanPage({ jobId }: { jobId: string }) {
  const { user, error: sessionError, refresh } = useAuth();
  const [choices, setChoices] = useState<ResumeChoice[] | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(selectedVersionFromLocation);
  const [response, setResponse] = useState<PlanResponse | null>(null);
  const [choicesError, setChoicesError] = useState("");
  const [planError, setPlanError] = useState("");
  const [choicesAttempt, setChoicesAttempt] = useState(0);
  const [planAttempt, setPlanAttempt] = useState(0);

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
    setPlanError("");
    if (
      !user ||
      choices === null ||
      !selectedVersionId ||
      !choices.some((choice) => choice.version.id === selectedVersionId)
    ) return;
    const ownerId = user.id;
    let active = true;
    apiClient.getResumeImprovementPlan(jobId, selectedVersionId)
      .then((plan) => {
        if (active) setResponse({ ownerId, jobId, resumeVersionId: selectedVersionId, plan });
      })
      .catch((reason) => {
        if (!active) return;
        setPlanError(authErrorMessage(reason));
        if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
      });
    return () => { active = false; };
  }, [choices, jobId, planAttempt, refresh, selectedVersionId, user]);

  const plan = response && response.ownerId === user?.id && response.jobId === jobId && response.resumeVersionId === selectedVersionId
    ? response.plan
    : null;
  return (
    <main className="auth-shell dashboard-shell plan-shell">
      <Link href="/" className="brand">StudentSuccessful</Link>
      <p className="fit-back"><Link href="/jobs">Back to jobs</Link></p>
      {sessionError ? <p role="alert" className="auth-error">{sessionError}</p>
        : user === undefined ? <p role="status">Checking your session…</p>
          : user === null ? <p>Please <Link href="/login">Login</Link> to view a resume improvement plan.</p>
            : choicesError ? <ResumeImprovementPlanFailure message={choicesError} retry={() => setChoicesAttempt((value) => value + 1)} />
              : choices === null ? <ResumeImprovementPlanLoading />
                : choices.length === 0 ? <section className="auth-card dashboard-card"><h1 className="profile-title">Resume Improvement Plan</h1><p className="muted">Upload a resume version before viewing a plan.</p><Link className="secondary" href="/resumes">Manage resumes</Link></section>
                  : <>
                    <section className="auth-card dashboard-card plan-selector">
                      <label htmlFor="resume-version-select">Choose a resume version</label>
                      <select
                        id="resume-version-select"
                        value={selectedVersionId ?? ""}
                        onChange={(event) => setSelectedVersionId(event.target.value || null)}
                      >
                        {choices.map((choice) => <option key={choice.version.id} value={choice.version.id}>{choice.resumeTitle} — version {choice.version.version_number}</option>)}
                      </select>
                    </section>
                    {plan ? <ResumeImprovementPlanContent plan={plan} />
                      : planError ? <ResumeImprovementPlanFailure message={planError} retry={() => setPlanAttempt((value) => value + 1)} />
                        : <ResumeImprovementPlanLoading />}
                  </>}
    </main>
  );
}
