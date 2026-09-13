import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  ResumeTailoringDraftAction,
  ResumeTailoringDraftContent,
  ResumeTailoringDraftFailure,
  ResumeTailoringDraftLoading,
  ResumeTailoringDraftPage,
} from "../../components/jobs/ResumeTailoringDraftPage";
import { ApiClient, type CurrentUser, type ResumeTailoringDraft } from "../api/client";

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

const plan: ResumeTailoringDraft = {
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  resume_id: "resume-1",
  resume_title: "Software resume",
  resume_version_id: "version-1",
  resume_version_number: 1,
  keep: [{
    category: "SKILL", action: "KEEP", requirement_id: "skill-1", name: "Python", importance: "REQUIRED", description: "Build services",
    reason: "Accepted evidence is already shown.", limitation: "Evidence is not proficiency verification.", sources: [selectedResumeSource], draft_text: null,
  }],
  draft_suggestions: [
    {
      category: "SKILL", action: "CONSIDER_ADDING_EXISTING_EVIDENCE", requirement_id: "skill-2", name: "Docker", importance: "REQUIRED", description: null,
      reason: "The cited skill source supports this exact fragment.", limitation: "Review before use.", draft_text: "Docker.",
      sources: [{ source_type: "CONFIRMED_BY_USER", source_id: "user-skill", parser_confidence: null }],
    },
    {
      category: "SKILL", action: "CONSIDER_ADDING_EXISTING_EVIDENCE", requirement_id: "skill-3", name: "AWS", importance: "PREFERRED", description: null,
      reason: "The cited project technology supports this exact fragment.", limitation: "Review before use.", draft_text: "Cloud project — AWS.",
      sources: [{ source_type: "PROJECT", source_id: "project-1", project_id: "project-1", project_title: "Cloud project", parser_confidence: null }],
    },
  ],
  unsupported: [
    {
      category: "SKILL", action: "DO_NOT_CLAIM_WITHOUT_EVIDENCE", requirement_id: "skill-4", name: "Kubernetes", importance: "PREFERRED", description: null,
      reason: "No recorded supporting evidence supports adding this requirement.", limitation: "No draft is generated.", sources: [], draft_text: null,
    },
    {
      category: "SKILL", action: "CONSIDER_ADDING_EXISTING_EVIDENCE", requirement_id: "skill-5", name: "Terraform", importance: "PREFERRED", description: null,
      reason: "No selected-version source supports a draft.", limitation: "Another resume version is not used for a draft.", sources: [], draft_text: null,
    },
  ],
  manual_review: [{
    category: "EDUCATION", action: "MANUAL_REVIEW", requirement_id: "education-1", name: "BS", importance: null, description: null,
    reason: "This requirement is not evaluated.", limitation: "Manual review is needed.", sources: [], draft_text: null,
  }],
  limitations: ["Only exact cited sources are used."],
};

it("uses the generated selected-version draft endpoint with an encoded no-store GET", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => plan });
  vi.stubGlobal("fetch", fetch);
  await new ApiClient().getResumeTailoringDraft("job id", "version id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-draft?resume_version_id=version%20id",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal) }),
  );
});

it("renders source-cited drafts while unsupported and manual items have no generated text", () => {
  const html = render(h(ResumeTailoringDraftContent, { draft: plan }));
  for (const value of [
    "Resume Tailoring Draft", "Platform Engineer · Example Co", "Selected resume:", "Software resume, version 1",
    "DRAFT — REVIEW BEFORE USE", "Existing Evidence to Keep", "Evidence-Backed Draft Suggestions", "Unsupported Requirements", "Manual Review Items",
    "KEEP", "CONSIDER_ADDING_EXISTING_EVIDENCE", "DO_NOT_CLAIM_WITHOUT_EVIDENCE", "MANUAL_REVIEW",
    "Python", "Docker", "AWS", "Kubernetes", "Terraform", "BS", "Docker.", "Cloud project — AWS.",
    "Draft text", "Copy draft text", "Review Draft", "Confirmed by you", "Cloud project — recorded project technology source.",
    "Software resume, version 1, evidence item 3", "Draft limitations",
  ]) expect(html).toContain(value);
  expect(html).toContain("do not edit, save, or create a resume version");
  expect(html).not.toMatch(/expert|advanced|highly skilled|increase your hiring chance/i);

  const unsupportedItem = plan.unsupported?.[0];
  const manualItem = plan.manual_review?.[0];
  if (!unsupportedItem || !manualItem) throw new Error("Expected test draft groups.");
  const unsupported = render(h(ResumeTailoringDraftAction, {
    item: unsupportedItem, selectedVersionId: plan.resume_version_id,
  }));
  const manual = render(h(ResumeTailoringDraftAction, {
    item: manualItem, selectedVersionId: plan.resume_version_id,
  }));
  for (const item of [unsupported, manual]) {
    expect(item).not.toContain("Draft text");
    expect(item).not.toContain("Copy draft text");
  }
});

it("renders loading, retryable error, and signed-out states without private draft data", () => {
  expect(render(h(ResumeTailoringDraftLoading))).toContain('role="status"');
  const failure = render(h(ResumeTailoringDraftFailure, { message: "Please try again.", retry: vi.fn() }));
  expect(failure).toContain('role="alert"');
  expect(failure).toContain("Retry resume tailoring draft");
  authState.user = null;
  expect(render(h(ResumeTailoringDraftPage, { jobId: "job-1" }))).toContain("to view a resume tailoring draft.");
});

it("does not render a draft before an authenticated request completes", () => {
  authState.user = {
    id: "owner", email: "owner@example.com", is_active: true,
    created_at: "2026-09-10T00:00:00Z", onboarding_completed_at: null,
  };
  const html = render(h(ResumeTailoringDraftPage, { jobId: "job-1" }));
  expect(html).toContain("Loading resume tailoring draft…");
  expect(html).not.toContain("Software resume");
});
