import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { ApiClient, type Resume, type ResumeEvidence, type ResumeExtractedText, type ResumeVersion } from "../api/client";
import { EvidencePanel, ResumeSummary } from "../../components/resumes/ResumesPage";

const resume: Resume = { id: "resume-one", title: "Backend Resume", created_at: "2026-09-08T00:00:00Z" };
const version: ResumeVersion = {
  id: "version-one", resume_id: resume.id, version_number: 1, file_format: "PDF", file_size_bytes: 128,
  file_hash_sha256: "a".repeat(64), is_primary_active: true, parse_status: "PENDING", created_at: "2026-09-08T00:00:00Z",
};

function respond(body: unknown, status = 200) {
  const fetch = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("uses generated resume paths, methods, and a current CSRF value for family mutations", async () => {
  vi.stubGlobal("document", { cookie: "ss_csrf=first" });
  const fetch = respond(resume, 201), client = new ApiClient();
  await client.createResume({ title: resume.title });
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resumes", expect.objectContaining({
    method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", "X-CSRF-Token": "first" }, body: JSON.stringify({ title: resume.title }),
  }));
  (document as { cookie: string }).cookie = "ss_csrf=second";
  await client.updateResume(resume.id, { title: "Renamed Resume" });
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resumes/resume-one", expect.objectContaining({ method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": "second" } }));
  await client.deleteResume(resume.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resumes/resume-one", expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "second" } }));
});

it("uploads one named file as multipart, lists versions, selects a primary, and deletes only that version", async () => {
  vi.stubGlobal("document", { cookie: "ss_csrf=token" });
  const fetch = respond(version, 201), client = new ApiClient();
  const file = new File(["%PDF-1.7"], "backend.pdf", { type: "application/pdf" });
  await client.uploadResumeVersion(resume.id, file);
  const upload = fetch.mock.calls[0];
  expect(upload[0]).toBe("/api/v1/resumes/resume-one/versions");
  expect(upload[1]).toEqual(expect.objectContaining({ method: "POST", credentials: "same-origin", cache: "no-store", headers: { "X-CSRF-Token": "token" } }));
  expect((upload[1] as RequestInit).body).toBeInstanceOf(FormData);
  expect(((upload[1] as RequestInit).body as FormData).get("file")).toMatchObject({ name: "backend.pdf", size: file.size, type: "application/pdf" });
  await client.listResumeVersions(resume.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resumes/resume-one/versions", expect.objectContaining({ method: "GET" }));
  await client.setResumePrimaryVersion(resume.id, { version_id: version.id });
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resumes/resume-one/primary-version", expect.objectContaining({ method: "PUT", body: JSON.stringify({ version_id: version.id }), headers: { "Content-Type": "application/json", "X-CSRF-Token": "token" } }));
  await client.deleteResumeVersion(version.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resume-versions/version-one", expect.objectContaining({ method: "DELETE" }));
  expect(client.resumeVersionFileUrl(version.id)).toBe("/api/v1/resume-versions/version-one/file");
});

it("keeps managed Resumes distinct from Career Artifact external links", () => {
  const html = render(h(ResumeSummary, { items: [resume] }));
  expect(html).toContain("managed resume family");
  expect(html).toContain("separate from Career Artifacts external links");
  expect(html).not.toContain("external_url");
});

it("uses the generated parsing and private evidence endpoints with a current CSRF token", async () => {
  vi.stubGlobal("document", { cookie: "ss_csrf=parse-token" });
  const fetch = respond(version), client = new ApiClient();
  await client.parseResumeVersion(version.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resume-versions/version-one/parse", expect.objectContaining({
    method: "POST", credentials: "same-origin", cache: "no-store", headers: { "X-CSRF-Token": "parse-token" },
  }));
  (document as { cookie: string }).cookie = "ss_csrf=renewed-token";
  await client.parseResumeVersion(version.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resume-versions/version-one/parse", expect.objectContaining({ headers: { "X-CSRF-Token": "renewed-token" } }));
  await client.listResumeEvidence(version.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resume-versions/version-one/evidence", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }));
  await client.getResumeExtractedText(version.id);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/resume-versions/version-one/extracted-text", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }));
});

it("labels evidence as detected rather than confirmed and renders a secondary raw-text view", () => {
  const evidence = [{ id: "evidence-one", category: "SKILLS", section_header: "Technical Skills", bullet_text: "Python and Docker", recognized_skills: [{ name: "Python" }, { name: "Docker" }] }] as ResumeEvidence[];
  const text = { raw_extracted_text: "Python and Docker" } as ResumeExtractedText;
  const html = render(h(EvidencePanel, { analysis: { state: "ready", evidence, text } }));
  expect(html).toContain("Detected from this resume");
  expect(html).toContain("Recognized skill evidence: Python, Docker");
  expect(html).toContain("not confirmed skills or profile claims");
  expect(html).toContain("Raw extracted text");
  expect(html).not.toContain("Confirmed skill");
});

it("renders explicit loading, error, and empty detected-evidence states", () => {
  expect(render(h(EvidencePanel, { analysis: { state: "loading", evidence: [], text: null } }))).toContain("Loading detected resume evidence");
  expect(render(h(EvidencePanel, { analysis: { state: "error", evidence: [], text: null } }))).toContain("Retry parsing to refresh it");
  expect(render(h(EvidencePanel, { analysis: { state: "ready", evidence: [], text: null } }))).toContain("No structured evidence was detected");
});
