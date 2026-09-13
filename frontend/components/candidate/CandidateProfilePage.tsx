"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError, apiClient, authErrorMessage, type CandidateProfile } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type Row = Record<string, unknown>;
type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: CandidateProfile };

function row(value: unknown): Row { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Row : {}; }
function rows(value: unknown): Row[] { return Array.isArray(value) ? value.map(row) : []; }
function text(value: unknown): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }
function values(data: Row, ...keys: string[]): Row[] { for (const key of keys) { const result = rows(data[key]); if (result.length || Array.isArray(data[key])) return result; } return []; }
function title(item: Row, fallback: string): string { return text(item.name) || text(item.title) || text(item.skill_name) || text(item.institution_name) || text(item.employer_name) || text(item.country_code) || fallback; }
function join(item: Row, keys: string[]): string { return keys.map(key => text(item[key])).filter(Boolean).join(" · "); }

function sourceLabel(source: Row): string {
  const kind = text(source.source_type || source.type || source.kind).toUpperCase();
  if (kind.includes("CONFIRM") || kind.includes("USER")) return "Added by you";
  if (kind.includes("PROJECT")) {
    const project = row(source.project);
    const name = join(source, ["project_title", "project_name", "title"]) || text(project.title);
    return `Used in project${name ? ` · ${name}` : ""}`;
  }
  if (kind.includes("RESUME") || kind.includes("EVIDENCE")) return resumeLabel(source);
  return text(source.label) || "Source recorded by StudentSuccessful";
}
function resumeLabel(item: Row): string {
  const resume = row(item.resume);
  const versionRow = row(item.resume_version);
  const name = join(item, ["resume_title", "resume_name"]) || text(resume.title);
  const version = text(item.resume_version_number || item.version_number || item.version) || text(versionRow.version_number);
  return `Found in resume${name ? ` · ${name}${version ? ` v${version}` : ""}` : version ? ` · v${version}` : ""}`;
}
function SourceList({ sources }: { sources: Row[] }) {
  return sources.length ? <ul className="candidate-sources">{sources.map((source, index) => <li key={`${sourceLabel(source)}-${index}`}>{sourceLabel(source)}</li>)}</ul> : <p className="muted">Source information is unavailable.</p>;
}
function Section({ title, children }: { title: string; children: React.ReactNode }) { return <section className="auth-card dashboard-card" aria-label={title}><h2>{title}</h2>{children}</section>; }

function ConfirmedSkills({ data }: { data: Row }) {
  const explicit = values(data, "confirmed_skills", "user_skills");
  const allSkills = [...values(data, "skills", "reconciled_skills"), ...values(data, "custom_skills")];
  const skills = explicit.length ? explicit : allSkills.filter(skill => values(skill, "sources", "provenance").some(source => {
    const kind = text(source.source_type || source.type || source.kind).toUpperCase();
    return kind.includes("CONFIRM") || kind.includes("USER");
  }));
  return <Section title="Confirmed Skills">{skills.length ? <ul>{skills.map((skill, index) => <li key={`${title(skill, "Skill")}-${index}`}><strong>{title(skill, "Unnamed skill")}</strong><p className="muted">Added by you</p></li>)}</ul> : <p className="muted">No confirmed skills added by you yet.</p>}</Section>;
}
function ReconciledSkills({ data }: { data: Row }) {
  const skills = [...values(data, "skills", "reconciled_skills"), ...values(data, "custom_skills")];
  return <Section title="Skills and Sources"><p className="muted">Sources are shown separately. Resume references and project use do not confirm a skill.</p>{skills.length ? <ul>{skills.map((skill, index) => <li key={`${title(skill, "Skill")}-${index}`}><strong>{title(skill, "Unnamed skill")}</strong><SourceList sources={values(skill, "sources", "provenance")} /></li>)}</ul> : <p className="muted">No skills with recorded sources yet.</p>}</Section>;
}
function ResumeEvidence({ data }: { data: Row }) {
  const evidence = values(data, "resume_evidence", "detected_resume_evidence", "evidence");
  return <Section title="Detected Resume Evidence"><p className="muted">Found in resume. Detected references are not confirmed skills or profile claims.</p>{evidence.length ? <ul>{evidence.map((item, index) => { const recognized = values(item, "recognized_skills").map(skill => text(skill.name)).filter(Boolean); return <li key={`${text(item.id) || text(item.bullet_text)}-${index}`}><strong>{text(item.section_header) || text(item.category) || "Resume reference"}</strong><p>{text(item.bullet_text) || text(item.text)}</p><p className="muted">{resumeLabel(item)}</p>{recognized.length ? <p className="muted">Recognized skill evidence: {recognized.join(", ")} (detected; not confirmed)</p> : null}</li>; })}</ul> : <p className="muted">No resume evidence detected yet.</p>}</Section>;
}
function Records({ title: heading, data, keys, empty, detail }: { title: string; data: Row; keys: string[]; empty: string; detail: (item: Row) => string }) {
  const items = values(data, ...keys);
  return <Section title={heading}>{items.length ? <ul>{items.map((item, index) => <li key={`${text(item.id) || title(item, heading)}-${index}`}><strong>{title(item, heading.slice(0, -1))}</strong>{detail(item) && <p className="muted">{detail(item)}</p>}<p className="muted">Added by you</p></li>)}</ul> : <p className="muted">{empty}</p>}</Section>;
}
function ApplicationProfile({ data }: { data: Row }) {
  const profile = row(data.profile);
  const fields: [string, string][] = [["legal_first_name", "Legal first name"], ["legal_last_name", "Legal last name"], ["preferred_name", "Preferred name"], ["phone_number", "Phone number"], ["address_city", "City"], ["address_country_code", "Country"]];
  return <Section title="Application Profile">{Object.keys(profile).length ? <><p className="muted">Added by you</p><dl>{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{text(profile[key]) || "Not provided"}</dd></div>)}</dl></> : <p className="muted">No application profile saved yet.</p>}</Section>;
}
function Preferences({ data }: { data: Row }) {
  const preferences = row(data.preferences);
  const display = (value: unknown): string => Array.isArray(value) ? value.map(item => typeof item === "string" ? item : text(row(item).value)).filter(item => item.trim()).join(", ") : text(value);
  const entries = Object.entries(preferences).map(([key, value]) => [key, display(value)] as const).filter(([, value]) => value.trim());
  return <Section title="Preferences"><p className="muted">Saved career preferences are separate from skills and resume evidence.</p>{entries.length ? <><p className="muted">Added by you</p><dl>{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl></> : <p className="muted">No career preferences saved yet.</p>}</Section>;
}
export function CandidateSections({ data }: { data: CandidateProfile }) {
  const profile = row(data);
  return <div className="dashboard-grid candidate-grid">
    <ApplicationProfile data={profile} />
    <ConfirmedSkills data={profile} />
    <ReconciledSkills data={profile} />
    <ResumeEvidence data={profile} />
    <Records title="Projects" data={profile} keys={["projects"]} empty="No projects saved yet." detail={item => text(item.description)} />
    <Records title="Education" data={profile} keys={["education"]} empty="No education records saved yet." detail={item => join(item, ["degree_level", "major", "institution_name"])} />
    <Records title="Employment" data={profile} keys={["employment"]} empty="No employment records saved yet." detail={item => join(item, ["job_title", "employer_name"])} />
    <Records title="Work Authorization" data={profile} keys={["work_authorization", "work_authorizations"]} empty="No work authorization records saved yet." detail={item => join(item, ["authorization_status", "country_code"])} />
    <Preferences data={profile} />
  </div>;
}

export function CandidateProfilePage() {
  const { user, error: sessionError, refresh } = useAuth();
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setState({ status: "loading" });
    apiClient.getCandidateProfile().then(data => { if (active) setState({ status: "ready", data }); }).catch(error => {
      if (!active) return;
      setState({ status: "error", message: authErrorMessage(error) });
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    });
    return () => { active = false; };
  }, [attempt, refresh, user]);

  return <main className="auth-shell dashboard-shell"><Link href="/" className="brand">StudentSuccessful</Link><h1 className="profile-title">Candidate Profile</h1><p className="muted">A source-aware view of saved facts, project use, and detected resume references.</p>
    {sessionError ? <p role="alert" className="auth-error">{sessionError}</p> : user === undefined ? <p role="status">Checking your session…</p> : user === null ? <p>Please <Link href="/login">Login</Link> to view your Candidate Profile.</p> : state.status === "loading" ? <p role="status">Loading Candidate Profile…</p> : state.status === "error" ? <><p role="alert" className="auth-error">Could not load Candidate Profile. {state.message}</p><button className="secondary" onClick={() => setAttempt(value => value + 1)}>Retry Candidate Profile</button></> : <CandidateSections data={state.data} />}
  </main>;
}
