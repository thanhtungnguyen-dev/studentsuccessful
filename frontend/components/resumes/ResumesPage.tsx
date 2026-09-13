"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, apiClient, authErrorMessage, type Resume, type ResumeEvidence, type ResumeExtractedText, type ResumeVersion } from "../../lib/api/client";
import { useAuth } from "../auth/AuthProvider";
import { PortfolioPage } from "../portfolio/PortfolioPage";

const MAX_FILE_BYTES = 5 * 1024 * 1024;
function displayDate(value: string): string { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(value)); }
function displayBytes(bytes: number): string { return `${(bytes / 1024 / 1024).toFixed(bytes < 1024 * 1024 ? 2 : 1)} MB`; }
function allowedFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension !== "pdf" && extension !== "docx") return "Choose a PDF or DOCX file.";
  if (file.size > MAX_FILE_BYTES) return "Files must be 5 MB or smaller.";
  return null;
}
type Analysis = { state: "loading" | "ready" | "error"; evidence: ResumeEvidence[]; text: ResumeExtractedText | null };
function record(value: unknown): Record<string, unknown> { return value !== null && typeof value === "object" ? value as Record<string, unknown> : {}; }
function valueText(value: unknown): string { return typeof value === "string" ? value : ""; }
function evidenceSkills(item: ResumeEvidence): string[] {
  const row = record(item);
  const values = Array.isArray(row.recognized_skills) ? row.recognized_skills : [];
  return values.map(value => valueText(record(value).name)).filter(Boolean);
}
function extractedText(value: ResumeExtractedText | null): string {
  const row = record(value);
  return valueText(row.raw_extracted_text);
}

export function EvidencePanel({ analysis }: { analysis: Analysis }) {
  if (analysis.state === "loading") return <p className="muted" role="status">Loading detected resume evidence…</p>;
  if (analysis.state === "error") return <p className="muted">Detected resume evidence could not be loaded. Retry parsing to refresh it.</p>;
  return <section className="resume-evidence"><h4>Detected from this resume</h4><p className="muted">These are parser-detected references from this file, not confirmed skills or profile claims.</p>
    {analysis.evidence.length ? <ul>{analysis.evidence.map(item => { const row = record(item), skills = evidenceSkills(item); return <li key={valueText(row.id) || valueText(row.bullet_text)}><strong>{valueText(row.section_header) || valueText(row.category) || "Other"}</strong><p>{valueText(row.bullet_text)}</p>{skills.length ? <p className="muted">Recognized skill evidence: {skills.join(", ")}</p> : null}</li>; })}</ul> : <p className="muted">No structured evidence was detected from this resume.</p>}
    {extractedText(analysis.text) ? <details><summary>Raw extracted text</summary><pre>{extractedText(analysis.text)}</pre></details> : null}
  </section>;
}

export function ResumeSummary({ items }: { items: Resume[] }) {
  return <>{items.length ? <p>{items.length} managed {items.length === 1 ? "resume family" : "resume families"}</p> : <p className="muted">No uploaded resume families yet.</p>}<p className="muted">Uploaded files and version history are separate from Career Artifacts external links.</p></>;
}

export function ResumesPage() { return <PortfolioPage title="Resumes"><ResumeContent /></PortfolioPage>; }

function ResumeContent() {
  const { refresh } = useAuth();
  const [items, setItems] = useState<Resume[] | null>(null);
  const [versions, setVersions] = useState<Record<string, ResumeVersion[]>>({});
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Resume | "new" | null>(null);
  const [title, setTitle] = useState("");
  const [deletingFamily, setDeletingFamily] = useState<string | null>(null);
  const [deletingVersion, setDeletingVersion] = useState<string | null>(null);
  const [uploadingFor, setUploadingFor] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<Record<string, Analysis>>({});
  const [parsing, setParsing] = useState<Record<string, boolean>>({});
  const [parseErrors, setParseErrors] = useState<Record<string, string>>({});
  const pending = useRef(false);

  function failure(reason: unknown) {
    setError(authErrorMessage(reason));
    if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
  }
  useEffect(() => {
    let active = true;
    async function load() {
      setError("");
      const resumes = await apiClient.listResumes();
      const histories = await Promise.all(resumes.map(async resume => [resume.id, await apiClient.listResumeVersions(resume.id)] as const));
      if (!active) return;
      setItems(resumes); setVersions(Object.fromEntries(histories));
      histories.flatMap(([, rows]) => rows).filter(version => version.parse_status === "PARSED_SUCCESS" || version.parse_status === "PARSE_FAILED").forEach(version => { void loadAnalysis(version.id, active); });
    }
    void load().catch(reason => {
      if (!active) return;
      setError(authErrorMessage(reason));
      if (reason instanceof ApiError && reason.status === 401) void refresh().catch(() => {});
    });
    return () => { active = false; };
  }, [attempt, refresh]);

  async function loadAnalysis(versionId: string, active = true) {
    setAnalysis(existing => ({ ...existing, [versionId]: { state: "loading", evidence: existing[versionId]?.evidence ?? [], text: existing[versionId]?.text ?? null } }));
    try {
      const [evidence, text] = await Promise.all([apiClient.listResumeEvidence(versionId), apiClient.getResumeExtractedText(versionId)]);
      if (active) setAnalysis(existing => ({ ...existing, [versionId]: { state: "ready", evidence, text } }));
    } catch {
      if (active) setAnalysis(existing => ({ ...existing, [versionId]: { state: "error", evidence: existing[versionId]?.evidence ?? [], text: existing[versionId]?.text ?? null } }));
    }
  }

  async function parse(version: ResumeVersion) {
    if (pending.current || parsing[version.id]) return;
    pending.current = true; setBusy(true); setError(""); setSuccess(""); setParseErrors(existing => ({ ...existing, [version.id]: "" })); setParsing(existing => ({ ...existing, [version.id]: true }));
    try {
      const saved = await apiClient.parseResumeVersion(version.id);
      setVersions(existing => Object.fromEntries(Object.entries(existing).map(([resumeId, rows]) => [resumeId, rows.map(row => row.id === saved.id ? saved : row)])));
      if (saved.parse_status === "PARSED_SUCCESS") { setSuccess(`Version ${saved.version_number} parsed.`); void loadAnalysis(saved.id); }
      else setParseErrors(existing => ({ ...existing, [version.id]: "This resume could not be parsed. You can retry." }));
    } catch (reason) { const message = authErrorMessage(reason); setParseErrors(existing => ({ ...existing, [version.id]: message })); failure(reason); }
    finally { pending.current = false; setBusy(false); setParsing(existing => ({ ...existing, [version.id]: false })); }
  }

  async function saveFamily() {
    if (!items || !editing || pending.current) return;
    const cleanTitle = title.trim();
    if (!cleanTitle) { setError("Enter a resume title."); return; }
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      const saved = editing === "new" ? await apiClient.createResume({ title: cleanTitle }) : await apiClient.updateResume(editing.id, { title: cleanTitle });
      setItems(editing === "new" ? [...items, saved] : items.map(item => item.id === saved.id ? saved : item));
      if (editing === "new") setVersions(existing => ({ ...existing, [saved.id]: [] }));
      setEditing(null); setTitle(""); setSuccess(editing === "new" ? "Resume family created." : "Resume family renamed.");
    } catch (reason) { failure(reason); }
    finally { pending.current = false; setBusy(false); }
  }
  async function removeFamily() {
    if (!items || !deletingFamily || pending.current) return;
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      await apiClient.deleteResume(deletingFamily);
      setItems(items.filter(item => item.id !== deletingFamily));
      setVersions(existing => { const next = { ...existing }; delete next[deletingFamily]; return next; });
      setDeletingFamily(null); setSuccess("Resume family and its uploaded versions removed.");
    } catch (reason) { failure(reason); }
    finally { pending.current = false; setBusy(false); }
  }
  async function upload(resume: Resume) {
    if (!file || pending.current) return;
    const validation = allowedFile(file); if (validation) { setError(validation); return; }
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      const saved = await apiClient.uploadResumeVersion(resume.id, file);
      setVersions(existing => ({ ...existing, [resume.id]: [...(existing[resume.id] ?? []), saved].sort((a, b) => b.version_number - a.version_number) }));
      setUploadingFor(null); setFile(null); setSuccess(`Version ${saved.version_number} uploaded.`);
    } catch (reason) { failure(reason); }
    finally { pending.current = false; setBusy(false); }
  }
  async function makePrimary(resume: Resume, version: ResumeVersion) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      const saved = await apiClient.setResumePrimaryVersion(resume.id, { version_id: version.id });
      setVersions(existing => ({ ...existing, [resume.id]: (existing[resume.id] ?? []).map(row => row.id === saved.id ? saved : { ...row, is_primary_active: false }) }));
      setSuccess(`Version ${saved.version_number} is now primary.`);
    } catch (reason) { failure(reason); }
    finally { pending.current = false; setBusy(false); }
  }
  async function removeVersion() {
    if (!deletingVersion || pending.current) return;
    const version = Object.values(versions).flat().find(row => row.id === deletingVersion);
    if (!version) return;
    pending.current = true; setBusy(true); setError(""); setSuccess("");
    try {
      await apiClient.deleteResumeVersion(version.id);
      setVersions(existing => Object.fromEntries(Object.entries(existing).map(([resumeId, rows]) => [resumeId, rows.filter(row => row.id !== version.id)])));
      setDeletingVersion(null); setSuccess(`Version ${version.version_number} removed.`);
    } catch (reason) { failure(reason); }
    finally { pending.current = false; setBusy(false); }
  }

  return <>
    <p className="muted">Upload and keep versions of files StudentSuccessful manages. Career Artifacts remain separate external links; neither area changes the other.</p>
    {error && <p role="alert" className="auth-error">{error}</p>}{success && <p role="status" className="profile-success">{success}</p>}
    {items === null ? error ? <button className="secondary" onClick={() => setAttempt(value => value + 1)}>Retry resumes</button> : <p role="status">Loading resumes…</p> : <>
      {!editing && !deletingFamily && !deletingVersion && !uploadingFor && <button className="primary education-add" onClick={() => { setEditing("new"); setTitle(""); setError(""); setSuccess(""); }}>Create resume family</button>}
      {editing && <form className="auth-card education-form" onSubmit={event => { event.preventDefault(); void saveFamily(); }} noValidate><h2>{editing === "new" ? "Create resume family" : "Rename resume family"}</h2><fieldset disabled={busy}>
        <label htmlFor="resume-title">Resume title</label><input id="resume-title" value={title} maxLength={150} required onChange={event => setTitle(event.target.value)} />
        <div className="auth-actions"><button className="primary" type="submit">{busy ? "Saving…" : editing === "new" ? "Create family" : "Save name"}</button><button className="secondary" type="button" onClick={() => setEditing(null)}>Cancel</button></div>
      </fieldset></form>}
      <div className="education-list">
        {!items.length && <p className="muted">Create a resume family, then upload its first PDF or DOCX version.</p>}
        {items.map(resume => <article className="auth-card dashboard-card resume-card" key={resume.id}>
          <header><div><h2>{resume.title}</h2><p className="muted">Managed uploaded files · created {displayDate(resume.created_at)}</p></div>{(versions[resume.id] ?? []).some(version => version.is_primary_active) && <span className="resume-primary">Primary version selected</span>}</header>
          {uploadingFor === resume.id ? <form className="resume-upload" onSubmit={event => { event.preventDefault(); void upload(resume); }}><fieldset disabled={busy}><label htmlFor={`resume-file-${resume.id}`}>PDF or DOCX (5 MB maximum)</label><input id={`resume-file-${resume.id}`} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required onChange={event => { const next = event.currentTarget.files?.[0] ?? null; setFile(next); setError(next ? allowedFile(next) ?? "" : ""); }} />
            <div className="auth-actions"><button className="primary" type="submit">{busy ? "Uploading…" : "Upload version"}</button><button className="secondary" type="button" onClick={() => { setUploadingFor(null); setFile(null); }}>Cancel</button></div></fieldset></form> : !editing && !deletingFamily && !deletingVersion && <div className="auth-actions"><button className="primary" onClick={() => { setUploadingFor(resume.id); setFile(null); setError(""); setSuccess(""); }}>Upload new version</button><button className="secondary" onClick={() => { setEditing(resume); setTitle(resume.title); setError(""); setSuccess(""); }}>Rename</button><button className="secondary" onClick={() => setDeletingFamily(resume.id)}>Delete family</button></div>}
          {deletingFamily === resume.id && <section className="education-confirm"><p>Delete {resume.title} and every managed uploaded version? Career Artifacts and all other profile data will remain unchanged.</p><div className="auth-actions"><button className="secondary" disabled={busy} onClick={() => void removeFamily()}>{busy ? "Deleting…" : "Confirm delete family"}</button><button className="secondary" disabled={busy} onClick={() => setDeletingFamily(null)}>Cancel</button></div></section>}
          <section className="resume-history" aria-labelledby={`versions-${resume.id}`}><h3 id={`versions-${resume.id}`}>Version history</h3>{!(versions[resume.id] ?? []).length ? <p className="muted">No uploaded versions yet.</p> : <ul>{(versions[resume.id] ?? []).map(version => <li key={version.id} className="resume-version"><div><strong>Version {version.version_number}</strong>{version.is_primary_active && <span className="resume-primary"> Primary</span>}<p className="muted">{version.file_format} · {displayBytes(version.file_size_bytes)} · uploaded {displayDate(version.created_at)} · Parse status: {version.parse_status}</p></div>
            {parseErrors[version.id] && <p role="alert" className="auth-error">{parseErrors[version.id]}</p>}
            {deletingVersion === version.id ? <div className="auth-actions"><span>Delete this version? A primary version is not replaced automatically.</span><button className="secondary" disabled={busy} onClick={() => void removeVersion()}>{busy ? "Deleting…" : "Confirm delete"}</button><button className="secondary" disabled={busy} onClick={() => setDeletingVersion(null)}>Cancel</button></div> : !editing && !deletingFamily && !deletingVersion && !uploadingFor && <div className="auth-actions"><a className="secondary" href={apiClient.resumeVersionFileUrl(version.id)} target="_blank" rel="noopener noreferrer">Open file</a><button className="secondary" disabled={busy || parsing[version.id]} onClick={() => void parse(version)}>{parsing[version.id] ? "Parsing…" : version.parse_status === "PARSE_FAILED" || parseErrors[version.id] ? "Retry parse" : "Parse"}</button>{!version.is_primary_active && <button className="secondary" disabled={busy} onClick={() => void makePrimary(resume, version)}>Make primary</button>}<button className="secondary" disabled={busy} onClick={() => setDeletingVersion(version.id)}>Delete version</button></div>}
            {version.parse_status === "PARSE_FAILED" && !parseErrors[version.id] && <p className="muted">The last parse failed. Retry parsing when you are ready.</p>}
            {(version.parse_status === "PARSED_SUCCESS" || (version.parse_status === "PARSE_FAILED" && analysis[version.id])) && <EvidencePanel analysis={analysis[version.id] ?? { state: "loading", evidence: [], text: null }} />}</li>)}</ul>}</section>
        </article>)}
      </div>
    </>}
  </>;
}
