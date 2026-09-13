import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import {
  ResumeTailoringReviewContent,
  ResumeTailoringReviewPage,
} from "../../components/jobs/ResumeTailoringReviewPage";
import {
  ApiClient,
  type CurrentUser,
  type ResumeTailoringReview,
} from "../api/client";

const authState = vi.hoisted(() => ({ user: undefined as CurrentUser | null | undefined, error: "" }));
vi.mock("../../components/auth/AuthProvider", () => ({ useAuth: () => ({ ...authState, refresh: vi.fn() }) }));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  authState.user = undefined;
  authState.error = "";
});

const review: ResumeTailoringReview = {
  id: "review-1",
  status: "DRAFT",
  job_id: "job-1",
  job_title: "Platform Engineer",
  company_name: "Example Co",
  source_resume_version_id: "version-1",
  resume_title: "Software resume",
  resume_version_number: 1,
  created_at: "2026-09-11T00:00:00Z",
  updated_at: "2026-09-11T00:00:00Z",
  finalized_at: null,
  items: [
    {
      id: "item-docker",
      ordinal: 0,
      category: "SKILL",
      action: "CONSIDER_ADDING_EXISTING_EVIDENCE",
      requirement_id: "requirement-docker",
      name: "Docker",
      importance: "REQUIRED",
      description: "Build services",
      original_draft_text: "Docker.",
      reason: "The cited recorded source supports this draft fragment.",
      limitation: "Review the wording before future document use.",
      provenance: [{ source_type: "CONFIRMED_BY_USER", source_id: "user-skill" }],
      decision: "PENDING",
      user_edited_text: "Docker wording selected by the user.",
      created_at: "2026-09-11T00:00:00Z",
      updated_at: "2026-09-11T00:00:00Z",
    },
    {
      id: "item-aws",
      ordinal: 1,
      category: "SKILL",
      action: "CONSIDER_ADDING_EXISTING_EVIDENCE",
      requirement_id: "requirement-aws",
      name: "AWS",
      importance: "PREFERRED",
      description: null,
      original_draft_text: "Cloud project — AWS.",
      reason: "The cited project source supports this draft fragment.",
      limitation: "Review the wording before future document use.",
      provenance: [{ source_type: "PROJECT", source_id: "project-1", project_id: "project-1", project_title: "Cloud project" }],
      decision: "REJECTED",
      user_edited_text: null,
      created_at: "2026-09-11T00:00:00Z",
      updated_at: "2026-09-11T00:00:00Z",
    },
  ],
};

it("uses encoded no-store review reads and CSRF-protected review mutations", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => review });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("document", { cookie: "ss_csrf=current-token" });
  const client = new ApiClient();
  await client.getResumeTailoringReview("job id", "version id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-reviews?resume_version_id=version%20id",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }),
  );
  await client.createResumeTailoringReview("job id", { resume_version_id: "version id" });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-reviews",
    expect.objectContaining({ method: "POST", headers: { "X-CSRF-Token": "current-token", "Content-Type": "application/json" }, body: '{"resume_version_id":"version id"}', credentials: "same-origin", cache: "no-store" }),
  );
  await client.updateResumeTailoringReviewItem("job id", "review id", "item id", { decision: "ACCEPTED" });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-reviews/review%20id/items/item%20id",
    expect.objectContaining({ method: "PATCH", headers: { "X-CSRF-Token": "current-token", "Content-Type": "application/json" }, body: '{"decision":"ACCEPTED"}' }),
  );
  await client.finalizeResumeTailoringReview("job id", "review id");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/jobs/job%20id/resume-reviews/review%20id/finalize",
    expect.objectContaining({ method: "POST", headers: { "X-CSRF-Token": "current-token" }, credentials: "same-origin", cache: "no-store" }),
  );
});

it("renders original system drafts, visible provenance, and distinctly labeled user wording", () => {
  const html = render(h(ResumeTailoringReviewContent, {
    review,
    busy: false,
    onUpdate: vi.fn(),
    onFinalize: vi.fn(),
  }));
  for (const value of [
    "Resume Draft Review", "Platform Engineer · Example Co", "Software resume, version 1", "Review status:",
    "System draft", "Docker.", "Cloud project — AWS.", "Provenance", "Confirmed by you", "Cloud project — recorded project technology source.",
    "USER EDITED", "Docker wording selected by the user.", "not candidate evidence", "ACCEPT", "REJECT", "Save user edit", "Finalize review",
  ]) expect(html).toContain(value);
  expect(html).not.toMatch(/confirmed candidate fact|skill inference|new resume version/i);
});

it("makes finalized reviews visibly read-only", () => {
  const html = render(h(ResumeTailoringReviewContent, {
    review: { ...review, status: "FINALIZED", finalized_at: "2026-09-11T01:00:00Z" },
    busy: false,
    onUpdate: vi.fn(),
    onFinalize: vi.fn(),
  }));
  expect(html).toContain("Review finalized");
  expect(html).toContain("Read-only:");
  expect(html).not.toContain(">ACCEPT<");
  expect(html).not.toContain(">REJECT<");
  expect(html).not.toContain("Save user edit");
  expect(html).not.toContain("Confirm finalization");
});

it("keeps private review data out of signed-out and loading states", () => {
  authState.user = null;
  expect(render(h(ResumeTailoringReviewPage, { jobId: "job-1" }))).toContain("to review a resume draft.");
  authState.user = {
    id: "owner", email: "owner@example.com", is_active: true,
    created_at: "2026-09-11T00:00:00Z", onboarding_completed_at: null,
  };
  const html = render(h(ResumeTailoringReviewPage, { jobId: "job-1" }));
  expect(html).toContain("Loading resume versions…");
  expect(html).not.toContain("Docker wording selected by the user.");
});
