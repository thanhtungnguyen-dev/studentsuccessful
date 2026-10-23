"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowUpRight, BriefcaseBusiness, ChevronDown, CircleCheck,
  Code2, ExternalLink, FileText, FolderGit2, GraduationCap, MapPin,
  Search, ShieldCheck, UserRound,
} from "lucide-react";
import { LoadingState } from "../ui/LoadingState";
import { PageHeader } from "../ui/PageHeader";
import { ApiError, apiClient, authErrorMessage, type CandidateProfile } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";

type Row = Record<string, unknown>;
const COUNTRY_NAMES: Record<string, string> = { CA: "Canada", US: "United States" };
type State = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; data: CandidateProfile };

function row(value: unknown): Row { return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Row : {}; }
function rows(value: unknown): Row[] { return Array.isArray(value) ? value.map(row) : []; }
function text(value: unknown): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }
function values(data: Row, ...keys: string[]): Row[] { for (const key of keys) { const result = rows(data[key]); if (result.length || Array.isArray(data[key])) return result; } return []; }
function title(item: Row, fallback: string): string { return text(item.name) || text(item.title) || text(item.skill_name) || text(item.institution_name) || text(item.employer_name) || fallback; }
function join(item: Row, keys: string[]): string { return keys.map(key => text(item[key])).filter(Boolean).join(" · "); }

function sourceLabel(source: Row): string {
  const kind = text(source.source_type || source.type || source.kind).toUpperCase();
  if (kind.includes("CONFIRM") || kind.includes("USER")) return "Added to profile";
  if (kind.includes("PROJECT")) {
    const project = row(source.project);
    const name = join(source, ["project_title", "project_name", "title"]) || text(project.title);
    return `Project${name ? ` · ${name}` : ""}`;
  }
  if (kind.includes("RESUME") || kind.includes("EVIDENCE")) return resumeLabel(source);
  return text(source.label) || "Source recorded";
}
function resumeLabel(item: Row): string {
  const resume = row(item.resume);
  const versionRow = row(item.resume_version);
  const name = join(item, ["resume_title", "resume_name"]) || text(resume.title);
  const version = text(item.resume_version_number || item.version_number || item.version) || text(versionRow.version_number);
  return `Resume${name ? ` · ${name}${version ? ` v${version}` : ""}` : version ? ` · v${version}` : ""}`;
}

const SKILL_BRANDS: Record<string, { mark: string; tone: string }> = {
  python: { mark: "Py", tone: "python" },
  javascript: { mark: "JS", tone: "javascript" },
  typescript: { mark: "TS", tone: "typescript" },
  react: { mark: "⚛", tone: "react" },
  "c++": { mark: "C++", tone: "cpp" },
  "c/c++": { mark: "C++", tone: "cpp" },
  "c#": { mark: "C#", tone: "cpp" },
  postgresql: { mark: "PG", tone: "postgres" },
  sql: { mark: "DB", tone: "postgres" },
  git: { mark: "Git", tone: "git" },
  linux: { mark: "Lx", tone: "linux" },
  docker: { mark: "D", tone: "docker" },
  "next.js": { mark: "N", tone: "next" },
  "node.js": { mark: "JS", tone: "node" },
  fastapi: { mark: "F", tone: "fastapi" },
  java: { mark: "J", tone: "java" },
};
function TechMark({ name }: { name: string }) {
  const brand = SKILL_BRANDS[name.toLowerCase().trim()];
  if (brand?.tone === "python") {
    return <span className="candidate-tech-mark candidate-tech-mark--python"><Image src="/skill-icons/python.svg" width={26} height={26} alt="" unoptimized /></span>;
  }
  return <span className={`candidate-tech-mark candidate-tech-mark--${brand?.tone || "other"}`} aria-hidden="true">{brand?.mark || <Code2 size={17} strokeWidth={1.8} />}</span>;
}

function Panel({ title: heading, icon, href, children, className = "", count }: { title: string; icon: ReactNode; href?: string; children: ReactNode; className?: string; count?: number }) {
  return <section className={`auth-card dashboard-card candidate-panel ${className}`} aria-label={heading}>
    <header className="candidate-panel-header">
      <div className="candidate-panel-heading"><span className="candidate-panel-icon" aria-hidden="true">{icon}</span><h2>{heading}</h2>{count !== undefined && <span className="candidate-count">{count}</span>}</div>
      {href && <Link href={href} className="candidate-edit-link">Edit <ArrowUpRight size={15} aria-hidden="true" /></Link>}
    </header>
    {children}
  </section>;
}
function DisclosurePanel({ title: heading, count, icon, children, description }: { title: string; count: number; icon: ReactNode; children: ReactNode; description: string }) {
  return <details className="candidate-disclosure auth-card">
    <summary><span className="candidate-panel-heading"><span className="candidate-panel-icon" aria-hidden="true">{icon}</span><span className="candidate-disclosure-title">{heading}<small>{description}</small></span><span className="candidate-count">{count}</span></span><ChevronDown className="candidate-chevron" size={18} aria-hidden="true" /></summary>
    <div className="candidate-disclosure-content">{children}</div>
  </details>;
}
function ApplicationProfile({ data }: { data: Row }) {
  const profile = row(data.profile);
  const fields: [string, string][] = [["legal_first_name", "First name"], ["legal_last_name", "Last name"], ["preferred_name", "Preferred name"], ["phone_number", "Phone"], ["address_city", "City"], ["address_country_code", "Country"]];
  return <Panel title="Personal information" icon={<UserRound size={19} />} href="/profile" className="candidate-personal-panel">
    {Object.keys(profile).length ? <dl className="candidate-field-list">{fields.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{key === "address_country_code" ? (COUNTRY_NAMES[text(profile[key]).toUpperCase()] || text(profile[key]) || "Not provided") : (text(profile[key]) || "Not provided")}</dd></div>)}</dl> : <p className="candidate-empty">No personal information saved yet.</p>}
  </Panel>;
}
function ConfirmedSkills({ data }: { data: Row }) {
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const explicit = values(data, "confirmed_skills", "user_skills");
  const allSkills = [...values(data, "skills", "reconciled_skills"), ...values(data, "custom_skills")];
  const raw = explicit.length ? explicit : allSkills.filter(skill => values(skill, "sources", "provenance").some(source => {
    const kind = text(source.source_type || source.type || source.kind).toUpperCase();
    return kind.includes("CONFIRM") || kind.includes("USER");
  }));
  // Display an overlapping C/C++ label only once without changing saved evidence.
  const names = [...new Map(raw.map(skill => [title(skill, "").trim().toLowerCase(), title(skill, "")])).values()].filter(Boolean);
  const skills = names.filter(name => !(name === "C++" && names.some(other => other.toLowerCase() === "c/c++")))
    .sort((a, b) => a.localeCompare(b));
  const priority = ["Python", "React", "TypeScript", "JavaScript", "PostgreSQL", "SQL", "C/C++", "Linux", "Git"];
  const ordered = [...skills].sort((a, b) => {
    const rank = (skill: string) => {
      const index = priority.findIndex(item => item.toLowerCase() === skill.toLowerCase());
      return index < 0 ? priority.length : index;
    };
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  const matching = ordered.filter(skill => skill.toLowerCase().includes(query.trim().toLowerCase()));
  const visible = showAll || query ? matching : matching.slice(0, 9);
  return <Panel title="Confirmed skills" icon={<CircleCheck size={19} />} href="/skills" count={skills.length} className="candidate-skills-panel">
    {skills.length > 9 && <label className="candidate-skill-search"><Search size={17} aria-hidden="true" /><span className="sr-only">Find a skill</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Find a skill" /></label>}
    {matching.length ? <ul className="candidate-skill-grid">{visible.map(skill => <li key={skill} className="candidate-skill-chip"><TechMark name={skill} /><span>{skill}</span></li>)}</ul> : <p className="candidate-empty">{query ? "No skills match your search." : "Add your skills to build your profile."}</p>}
    {!query && skills.length > 9 && <button type="button" className="candidate-show-more" onClick={() => setShowAll(value => !value)} aria-expanded={showAll}>{showAll ? "Show fewer skills" : `Show all ${skills.length} skills`} <ChevronDown size={15} className={showAll ? "candidate-chevron-up" : ""} /></button>}
  </Panel>;
}
function ReconciledSkills({ data }: { data: Row }) {
  const skills = [...values(data, "skills", "reconciled_skills"), ...values(data, "custom_skills")];
  return <DisclosurePanel title="Skills & evidence" icon={<ShieldCheck size={19} />} count={skills.length} description="See where each skill was recorded">
    {skills.length ? <ul className="candidate-evidence-list">{skills.map((skill, index) => <li key={`${title(skill, "Skill")}-${index}`}><strong>{title(skill, "Unnamed skill")}</strong><ul className="candidate-source-tags">{values(skill, "sources", "provenance").map((source, i) => <li key={i}>{sourceLabel(source)}</li>)}</ul></li>)}</ul> : <p className="candidate-empty">No skill sources available.</p>}
  </DisclosurePanel>;
}
function ResumeEvidence({ data }: { data: Row }) {
  const evidence = values(data, "resume_evidence", "detected_resume_evidence", "evidence");
  return <DisclosurePanel title="Resume evidence" icon={<FileText size={19} />} count={evidence.length} description="Review references detected in resumes">
    <p className="candidate-help">Automatically detected references are not confirmed skills.</p>
    {evidence.length ? <ul className="candidate-evidence-list">{evidence.map((item, index) => { const recognized = values(item, "recognized_skills").map(skill => text(skill.name)).filter(Boolean); return <li key={`${text(item.id) || text(item.bullet_text)}-${index}`}><strong>{text(item.section_header) || text(item.category) || "Resume reference"}</strong><p>{text(item.bullet_text) || text(item.text)}</p><p className="candidate-help">{resumeLabel(item)}</p>{recognized.length ? <div className="candidate-source-tags">{recognized.map(skill => <span key={skill}>{skill}</span>)}</div> : null}</li>; })}</ul> : <p className="candidate-empty">No resume evidence found yet.</p>}
  </DisclosurePanel>;
}
function Records({ heading, data, keys, empty, detail, href, icon }: { heading: string; data: Row; keys: string[]; empty: string; detail: (item: Row) => string; href: string; icon: ReactNode }) {
  const items = values(data, ...keys);
  return <Panel title={heading} icon={icon} href={href} count={items.length}>
    {items.length ? <ul className="candidate-record-list">{items.slice(0, 3).map((item, index) => <li key={`${text(item.id) || title(item, heading)}-${index}`}><strong>{title(item, heading.slice(0, -1))}</strong>{detail(item) && <p>{detail(item)}</p>}</li>)}</ul> : <p className="candidate-empty">{empty}</p>}
    {items.length > 3 && <Link className="candidate-list-more" href={href}>View all {items.length} <ExternalLink size={14} aria-hidden="true" /></Link>}
  </Panel>;
}
function Preferences({ data }: { data: Row }) {
  const preferences = row(data.preferences);
  const display = (value: unknown): string => Array.isArray(value) ? value.map(item => typeof item === "string" ? item : text(row(item).value)).filter(item => item.trim()).join(", ") : text(value);
  const entries = Object.entries(preferences).map(([key, value]) => [key, display(value)] as const).filter(([, value]) => value.trim());
  return <DisclosurePanel title="Career preferences" icon={<MapPin size={19} />} count={entries.length} description="Saved interests, locations and work preferences">
    {entries.length ? <dl className="candidate-field-list">{entries.map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl> : <p className="candidate-empty">No career preferences saved yet.</p>}
    <Link className="candidate-list-more" href="/preferences">Edit preferences <ArrowUpRight size={14} /></Link>
  </DisclosurePanel>;
}
export function CandidateSections({ data }: { data: CandidateProfile }) {
  const profile = row(data);
  return <div className="candidate-overview">
    <div className="candidate-top-grid"><ApplicationProfile data={profile} /><ConfirmedSkills data={profile} /></div>
    <div className="candidate-section-heading"><h2>Experience & qualifications</h2></div>
    <div className="candidate-record-grid">
      <Records heading="Projects" data={profile} keys={["projects"]} empty="No projects yet." detail={item => text(item.description)} href="/projects" icon={<FolderGit2 size={19} />} />
      <Records heading="Education" data={profile} keys={["education"]} empty="No education records yet." detail={item => join(item, ["degree_level", "major", "institution_name"])} href="/education" icon={<GraduationCap size={19} />} />
      <Records heading="Employment" data={profile} keys={["employment"]} empty="No employment records yet." detail={item => join(item, ["job_title", "employer_name"])} href="/employment" icon={<BriefcaseBusiness size={19} />} />
      <Records heading="Work authorization" data={profile} keys={["work_authorization", "work_authorizations"]} empty="No work authorization records yet." detail={item => join(item, ["authorization_status", "country_code"])} href="/work-authorization" icon={<ShieldCheck size={19} />} />
    </div>
    <div className="candidate-section-heading candidate-evidence-heading"><h2>Additional details</h2><p>Open a section to review the supporting records.</p></div>
    <div className="candidate-more-grid"><ReconciledSkills data={profile} /><ResumeEvidence data={profile} /><Preferences data={profile} /></div>
  </div>;
}

export function CandidateProfilePage() {
  const { user, error: sessionError, refresh } = useAuth();
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!user) return;
    let active = true;
    setState(current => current.status === "ready" ? current : { status: "loading" });
    apiClient.getCandidateProfile().then(data => { if (active) setState({ status: "ready", data }); }).catch(error => {
      if (!active) return;
      setState({ status: "error", message: authErrorMessage(error) });
      if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {});
    });
    return () => { active = false; };
  }, [attempt, refresh, user]);
  return <main className="auth-shell dashboard-shell candidate-shell"><Link href="/" className="brand">StudentSuccessful</Link><PageHeader title="Candidate Profile" description="Review the details and skills saved to your profile." />
    {sessionError ? <p role="alert" className="auth-error">{sessionError}</p> : user === undefined ? <LoadingState label="Checking your session…" /> : user === null ? <p>Please <Link href="/login">Login</Link> to view your profile.</p> : state.status === "loading" ? <LoadingState label="Loading candidate profile…" /> : state.status === "error" ? <><p role="alert" className="auth-error">Could not load your profile. {state.message}</p><button className="secondary" onClick={() => setAttempt(value => value + 1)}>Retry</button></> : <CandidateSections data={state.data} />}
  </main>;
}
