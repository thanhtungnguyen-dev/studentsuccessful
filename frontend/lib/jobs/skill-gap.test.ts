import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  SkillGapContent,
  SkillGapFailure,
  SkillGapLoading,
  SkillGapPage,
} from "../../components/jobs/SkillGapPage";
import { ApiClient, type CurrentUser, type SkillGapAnalysis } from "../api/client";

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

const alternateResumeSource = {
  ...selectedResumeSource,
  source_id: "evidence-2",
  resume_version_id: "version-2",
  resume_version_number: 2,
  evidence_ordinal: 1,
} as const;

const analysis: SkillGapAnalysis = {
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-1",
  resume_version_number: 1,
  covered: [{
    category: "SKILL", classification: "COVERED", requirement_id: "skill-1", name: "Python", importance: "REQUIRED", description: "Build services",
    explanation: "Accepted exact catalog-skill evidence is shown on this selected resume version.",
    limitation: "Evidence is not proficiency verification.", sources: [selectedResumeSource],
  }],
  resume_presentation_gaps: [
    {
      category: "SKILL", classification: "RESUME_PRESENTATION_GAP", requirement_id: "skill-2", name: "Docker", importance: "REQUIRED", description: null,
      explanation: "Recorded candidate evidence exists, but it is not shown on this resume.",
      limitation: "This source is not resume evidence.",
      sources: [{ source_type: "CONFIRMED_BY_USER", source_id: "user-skill", parser_confidence: null }],
    },
    {
      category: "SKILL", classification: "RESUME_PRESENTATION_GAP", requirement_id: "skill-3", name: "Terraform", importance: "PREFERRED", description: null,
      explanation: "Recorded candidate evidence exists, but it is not shown on this resume.",
      limitation: "Another version is not the selected version.", sources: [alternateResumeSource],
    },
  ],
  candidate_evidence_gaps: [{
    category: "SKILL", classification: "CANDIDATE_EVIDENCE_GAP", requirement_id: "skill-4", name: "AWS", importance: "PREFERRED", description: null,
    explanation: "No recorded supporting evidence for AWS.", limitation: "No recorded evidence is not an ability conclusion.", sources: [],
  }],
  unknown: [{
    category: "EDUCATION", classification: "UNKNOWN_UNASSESSED", requirement_id: "education-1", name: "BS", importance: null, description: null,
    explanation: "This education requirement is not evaluated.", limitation: "Education support is unknown.", sources: [],
  }],
  limitations: ["Only exact recorded sources are shown."],
};

it("uses the generated selected-version gap endpoint with an encoded no-store GET", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => analysis });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getJobSkillGaps("job id", "version id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/gaps?resume_version_id=version%20id",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal) }),
  );
});

it("renders all four classifications and provenance without an ability claim", () => {
  const html = render(h(SkillGapContent, { analysis }));
  for (const value of [
    "Skill gap analysis", "Platform Engineer · Example Co", "Selected resume:", "Software resume, version 1",
    "Covered", "Resume presentation gaps", "Candidate evidence gaps", "Unknown / unassessed",
    "Python", "Docker", "Terraform", "AWS", "BS", "Software resume, version 1, evidence item 3",
    "Confirmed by you", "Software resume, version 2, evidence item 1",
    "on another resume version; it is not shown on the selected version.",
    "Recorded candidate evidence exists, but it is not shown on this resume.",
    "No recorded supporting evidence.", "Analysis limitations",
  ]) expect(html).toContain(value);
  expect(html).toContain("does not assess ability, predict hiring outcomes, or recommend changes");
  expect(html).not.toMatch(/you don.t know|unqualified|need to learn/i);
});

it("renders loading, retryable error, and signed-out states without private analysis", () => {
  expect(render(h(SkillGapLoading))).toContain('role="status"');
  const failure = render(h(SkillGapFailure, { message: "Please try again.", retry: vi.fn() }));
  expect(failure).toContain('role="alert"');
  expect(failure).toContain("Retry skill gap analysis");
  authState.user = null;
  expect(render(h(SkillGapPage, { jobId: "job-1" }))).toContain("to view skill gap analysis.");
});

it("does not render a gap analysis before an authenticated request completes", () => {
  authState.user = {
    id: "owner", email: "owner@example.com", is_active: true,
    created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: null,
  };
  const html = render(h(SkillGapPage, { jobId: "job-1" }));
  expect(html).toContain("Loading skill gap analysis…");
  expect(html).not.toContain("Software resume");
});
