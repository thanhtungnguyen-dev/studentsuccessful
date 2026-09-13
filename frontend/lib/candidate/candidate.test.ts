import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { ApiClient, type CandidateProfile } from "../api/client";
import { CandidateSections } from "../../components/candidate/CandidateProfilePage";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("reads the private candidate view with same-origin no-store settings", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getCandidateProfile();
  expect(fetch).toHaveBeenCalledWith("/api/v1/profile/candidate", expect.objectContaining({ method: "GET", headers: {}, credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal) }));
});

it("keeps confirmed, resume, and project skill sources distinct", () => {
  const data: CandidateProfile = {
    facts_source: "ADDED_BY_USER",
    profile: { legal_first_name: "Ada", legal_last_name: "Lovelace" },
    skills: [{ name: "Python", sources: [
      { source_type: "CONFIRMED_BY_USER" },
      { source_type: "RESUME_EVIDENCE", resume_title: "Backend Resume", resume_version_number: 2 },
      { source_type: "PROJECT", project_title: "Cloud Deployment" },
    ] }],
    resume_evidence: [{ section_header: "Technical Skills", bullet_text: "Python and Docker", resume_title: "Backend Resume", resume_version_number: 2, recognized_skills: [{ name: "Python" }, { name: "Docker" }] }],
    projects: [{ title: "Cloud Deployment" }], education: [{ institution_name: "Example University" }], employment: [{ employer_name: "Example Employer" }], work_authorizations: [{ country_code: "CA" }], preferences: { work_modes: ["REMOTE"] },
  } as CandidateProfile;
  const html = render(h(CandidateSections, { data }));
  for (const expected of ["Application Profile", "Ada", "Confirmed Skills", "Added by you", "Skills and Sources", "Found in resume · Backend Resume v2", "Used in project · Cloud Deployment", "Detected Resume Evidence", "not confirmed skills or profile claims", "Recognized skill evidence: Python, Docker (detected; not confirmed)", "Preferences", "REMOTE"]) expect(html).toContain(expected);
  expect((html.match(/Added by you/g) ?? []).length).toBeGreaterThanOrEqual(6);
  expect(html).not.toContain("You have skill");
});

it("renders explicit empty source-aware states", () => {
  const html = render(h(CandidateSections, { data: { facts_source: "ADDED_BY_USER", preferences: { role_ids: [], industry_ids: [], location_ids: [], company_ids: [], skill_ids: [], work_modes: [], employment_types: [], custom_values: [] } } }));
  for (const expected of ["No application profile saved yet.", "No confirmed skills added by you yet.", "No skills with recorded sources yet.", "No resume evidence detected yet.", "No projects saved yet.", "No career preferences saved yet."]) expect(html).toContain(expected);
});
