import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  ResumeImprovementPlanContent,
  ResumeImprovementPlanFailure,
  ResumeImprovementPlanLoading,
  ResumeImprovementPlanPage,
} from "../../components/jobs/ResumeImprovementPlanPage";
import { ApiClient, type CurrentUser, type ResumeImprovementPlan } from "../api/client";

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

const plan: ResumeImprovementPlan = {
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-1",
  resume_version_number: 1,
  keep: [{
    category: "SKILL", action: "KEEP", requirement_id: "skill-1", name: "Python", importance: "REQUIRED", description: "Build services",
    reason: "Accepted evidence is already shown.", limitation: "Evidence is not proficiency verification.", sources: [selectedResumeSource],
  }],
  consider_adding_existing_evidence: [
    {
      category: "SKILL", action: "CONSIDER_ADDING_EXISTING_EVIDENCE", requirement_id: "skill-2", name: "Docker", importance: "REQUIRED", description: null,
      reason: "Recorded Docker evidence exists but is not shown on ResumeVersion 1.", limitation: "This source is not selected-resume evidence.",
      sources: [{ source_type: "CONFIRMED_BY_USER", source_id: "user-skill", parser_confidence: null }],
    },
    {
      category: "SKILL", action: "CONSIDER_ADDING_EXISTING_EVIDENCE", requirement_id: "skill-3", name: "Terraform", importance: "PREFERRED", description: null,
      reason: "Recorded Terraform evidence exists but is not shown on ResumeVersion 1.", limitation: "Another version is not the selected version.", sources: [alternateResumeSource],
    },
  ],
  do_not_claim_without_evidence: [{
    category: "SKILL", action: "DO_NOT_CLAIM_WITHOUT_EVIDENCE", requirement_id: "skill-4", name: "AWS", importance: "PREFERRED", description: null,
    reason: "No recorded supporting evidence supports adding AWS to this resume.", limitation: "No evidence is not an ability conclusion.", sources: [],
  }],
  manual_review: [{
    category: "EDUCATION", action: "MANUAL_REVIEW", requirement_id: "education-1", name: "BS", importance: null, description: null,
    reason: "This education requirement is not evaluated. Manual review is needed.", limitation: "Education support is unknown.", sources: [],
  }],
  limitations: ["Only exact recorded sources are used."],
};

it("uses the generated selected-version plan endpoint with an encoded no-store GET", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => plan });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getResumeImprovementPlan("job id", "version id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-plan?resume_version_id=version%20id",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal) }),
  );
});

it("renders all four conservative actions and their source distinctions", () => {
  const html = render(h(ResumeImprovementPlanContent, { plan }));
  for (const value of [
    "Resume Improvement Plan", "Platform Engineer · Example Co", "Selected resume:", "Software resume, version 1",
    "Already represented", "Existing evidence you may want to surface", "Do not claim without evidence", "Needs manual review",
    "KEEP", "CONSIDER_ADDING_EXISTING_EVIDENCE", "DO_NOT_CLAIM_WITHOUT_EVIDENCE", "MANUAL_REVIEW",
    "Python", "Docker", "Terraform", "AWS", "BS", "Software resume, version 1, evidence item 3",
    "Confirmed by you", "Software resume, version 2, evidence item 1",
    "on another resume version; it is not shown on the selected version.",
    "Recorded Docker evidence exists but is not shown on ResumeVersion 1.",
    "No recorded supporting evidence supports adding AWS to this resume.", "Plan limitations",
  ]) expect(html).toContain(value);
  expect(html).toContain("does not generate resume text, assess ability, or predict hiring outcomes");
  expect(html).not.toMatch(/increase your hiring chance|you don.t know|unqualified|need to learn/i);
});

it("renders loading, retryable error, and signed-out states without private plan data", () => {
  expect(render(h(ResumeImprovementPlanLoading))).toContain('role="status"');
  const failure = render(h(ResumeImprovementPlanFailure, { message: "Please try again.", retry: vi.fn() }));
  expect(failure).toContain('role="alert"');
  expect(failure).toContain("Retry resume improvement plan");
  authState.user = null;
  expect(render(h(ResumeImprovementPlanPage, { jobId: "job-1" }))).toContain("to view a resume improvement plan.");
});

it("does not render a plan before an authenticated request completes", () => {
  authState.user = {
    id: "owner", email: "owner@example.com", is_active: true,
    created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: null,
  };
  const html = render(h(ResumeImprovementPlanPage, { jobId: "job-1" }));
  expect(html).toContain("Loading resume improvement plan…");
  expect(html).not.toContain("Software resume");
});
