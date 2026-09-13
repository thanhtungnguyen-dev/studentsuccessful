import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  ResumeAlignmentContent,
  ResumeAlignmentFailure,
  ResumeAlignmentLoading,
  ResumeAlignmentPage,
} from "../../components/jobs/ResumeAlignmentPage";
import { ApiClient, type CurrentUser, type ResumeAlignment } from "../api/client";

const authState = vi.hoisted(() => ({ user: undefined as CurrentUser | null | undefined, error: "" }));
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: () => ({ ...authState, refresh: vi.fn() }) }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  authState.user = undefined;
  authState.error = "";
});

const selectedResumeSource = {
  source_type: "RESUME_EVIDENCE",
  source_id: "evidence-1",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-1",
  resume_version_number: 1,
  evidence_ordinal: 3,
  evidence_category: "SKILLS",
  evidence_section_header: "Skills",
  parser_confidence: "0.95",
  project_id: null,
  project_title: null,
} as const;

const alignment: ResumeAlignment = {
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-1",
  resume_version_number: 1,
  shown_on_resume: [{
    category: "SKILL", requirement_id: "skill-1", name: "Python", importance: "REQUIRED", description: "Build services",
    explanation: "Accepted exact catalog-skill evidence is shown on this selected resume version.",
    limitation: "Evidence is not proficiency verification.", sources: [selectedResumeSource],
  }],
  candidate_evidence_not_shown: [
    {
      category: "SKILL", requirement_id: "skill-2", name: "Docker", importance: "REQUIRED", description: null,
      explanation: "Recorded candidate evidence exists, but it is not shown in this resume version.",
      limitation: "This source is not resume evidence.",
      sources: [{ source_type: "CONFIRMED_BY_USER", source_id: "user-skill", parser_confidence: null }],
    },
    {
      category: "SKILL", requirement_id: "skill-3", name: "AWS", importance: "PREFERRED", description: null,
      explanation: "Recorded candidate evidence exists, but it is not shown in this resume version.",
      limitation: "This source is not resume evidence.",
      sources: [{ source_type: "PROJECT", source_id: "project-1", project_id: "project-1", project_title: "Cloud lab", parser_confidence: null }],
    },
  ],
  no_recorded_evidence: [{
    category: "SKILL", requirement_id: "skill-4", name: "Terraform", importance: "PREFERRED", description: null,
    explanation: "No accepted exact catalog-skill evidence is recorded.", limitation: "No recorded evidence is not an ability conclusion.", sources: [],
  }],
  unknown_unassessed: [{
    category: "EDUCATION", requirement_id: "education-1", name: "BS", importance: null, description: null,
    explanation: "This education requirement is not evaluated.", limitation: "Education support is unknown.", sources: [],
  }],
  limitations: ["Only exact recorded sources are shown."],
};

it("uses the generated exact-version endpoint with an encoded no-store GET", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => alignment });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getJobResumeAlignment("job id", "version id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-alignment?resume_version_id=version%20id",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal) }),
  );
});

it("renders selected-version identity, four outcomes, and source labels", () => {
  const html = render(h(ResumeAlignmentContent, { alignment }));
  for (const value of [
    "Resume alignment", "Platform Engineer · Example Co", "Selected resume:", "Software resume, version 1",
    "Shown on this resume", "Candidate evidence not shown", "No recorded evidence", "Unknown / unassessed",
    "Python", "Docker", "AWS", "Terraform", "BS", "Software resume, version 1, evidence item 3",
    "Confirmed by you", "Cloud lab", "Recorded candidate evidence exists, but it is not shown in this resume version.",
    "Alignment limitations",
  ]) expect(html).toContain(value);
  expect(html).toContain("does not assess ability, predict hiring outcomes, or recommend claims to add");
  expect(html).toContain("This does not mean you lack the capability.");
});

it("renders loading, retryable error, and signed-out states without private alignment", () => {
  expect(render(h(ResumeAlignmentLoading))).toContain('role="status"');
  const failure = render(h(ResumeAlignmentFailure, { message: "Please try again.", retry: vi.fn() }));
  expect(failure).toContain('role="alert"');
  expect(failure).toContain("Retry resume alignment");
  authState.user = null;
  expect(render(h(ResumeAlignmentPage, { jobId: "job-1" }))).toContain("to view resume alignment.");
});

it("does not render an alignment before an authenticated request completes", () => {
  authState.user = {
    id: "owner", email: "owner@example.com", is_active: true,
    created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: null,
  };
  const html = render(h(ResumeAlignmentPage, { jobId: "job-1" }));
  expect(html).toContain("Loading resume alignment…");
  expect(html).not.toContain("Software resume");
});
