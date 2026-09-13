import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  FitAnalysisContent,
  FitAnalysisFailure,
  FitAnalysisLoading,
  FitAnalysisPage,
} from "../../components/jobs/FitAnalysisPage";
import { ApiClient, type CurrentUser, type FitAnalysis } from "../api/client";

const authState = vi.hoisted(() => ({ user: undefined as CurrentUser | null | undefined, error: "" }));
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: () => ({ ...authState, refresh: vi.fn() }) }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  authState.user = undefined;
  authState.error = "";
});

const source = {
  source_type: "RESUME_EVIDENCE",
  source_id: "evidence-1",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-3",
  resume_version_number: 3,
  evidence_ordinal: 8,
  evidence_category: "SKILLS",
  evidence_section_header: "Skills",
  parser_confidence: "HIGH",
  project_id: null,
  project_title: null,
} as const;

const analysis: FitAnalysis = {
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  matched: [{
    category: "SKILL", requirement_id: "skill-1", name: "Python", importance: "REQUIRED", description: "Build services",
    explanation: "An exact catalog skill ID was recorded in candidate evidence.",
    limitation: "Resume evidence is not a verification of proficiency.", sources: [source],
  }],
  missing: [{
    category: "SKILL", requirement_id: "skill-2", name: "AWS", importance: "PREFERRED", description: null,
    explanation: "No candidate source references this skill.", limitation: "No recorded evidence is not a claim about capability.", sources: [],
  }],
  unknown: [{
    category: "EDUCATION", requirement_id: "education-1", name: "Bachelor's degree", importance: null, description: null,
    explanation: "Education records cannot determine this job requirement.", limitation: "Education support is unknown.", sources: [],
  }],
  limitations: ["Only recorded sources are shown."],
};

it("uses the generated fit endpoint with safe authenticated GET options", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => analysis });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getJobFit("job id");
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/jobs/job%20id/fit", expect.objectContaining({
    method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal),
  }));
});

it("renders explanations, all evidence sections, provenance, and source limitations", () => {
  const html = render(h(FitAnalysisContent, { analysis }));
  for (const value of [
    "Fit analysis", "Platform Engineer · Example Co", "Recorded evidence", "No recorded evidence", "Unknown",
    "Python", "AWS", "Bachelor&#x27;s degree", "Why this is listed:", "Limitation:", "Recorded sources",
    "Software resume, version 3, evidence item 8", "historical version", "No recorded sources.", "Analysis limitations",
  ]) expect(html).toContain(value);
  expect(html).toContain("does not assess ability, predict hiring outcomes, or make a recommendation");
  expect(html).toContain("This does not mean you lack the capability.");
});

it("renders loading, retryable error, and signed-out states", () => {
  expect(render(h(FitAnalysisLoading))).toContain('role="status"');
  const failure = render(h(FitAnalysisFailure, { message: "Please try again.", retry: vi.fn() }));
  expect(failure).toContain('role="alert"');
  expect(failure).toContain("Retry fit analysis");
  authState.user = null;
  expect(render(h(FitAnalysisPage, { jobId: "job-1" }))).toContain("to view a fit analysis.");
});

it("does not render an analysis before an authenticated request completes", () => {
  authState.user = { id: "owner", email: "owner@example.com", is_active: true, created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: null };
  const html = render(h(FitAnalysisPage, { jobId: "job-1" }));
  expect(html).toContain("Loading fit analysis…");
  expect(html).not.toContain("Software resume");
});
