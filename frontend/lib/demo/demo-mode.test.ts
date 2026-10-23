import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "../api/client";
import { isDemoModeEnabled } from "./config";
import { activateDemoSession, endDemoSession, resetDemoApiState } from "./demo-store";

describe("Frontend Demo Mode (NEXT_PUBLIC_DEMO_MODE)", () => {
  const originalEnv = process.env.NEXT_PUBLIC_DEMO_MODE;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_DEMO_MODE = "true";
    resetDemoApiState();
  });

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.NEXT_PUBLIC_DEMO_MODE;
    } else {
      process.env.NEXT_PUBLIC_DEMO_MODE = originalEnv;
    }
    vi.restoreAllMocks();
  });

  it("detects NEXT_PUBLIC_DEMO_MODE=true and NEXT_PUBLIC_DEMO_MODE=false", () => {
    process.env.NEXT_PUBLIC_DEMO_MODE = "true";
    expect(isDemoModeEnabled()).toBe(true);

    process.env.NEXT_PUBLIC_DEMO_MODE = "false";
    expect(isDemoModeEnabled()).toBe(false);
  });

  it("starts logged out on the public landing page until Demo CTA or login is triggered", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new ApiClient("http://localhost:8000");

    endDemoSession();
    const loggedOutUser = await client.getCurrentUser();
    expect(loggedOutUser).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();

    activateDemoSession();
    const user = await client.getCurrentUser();
    expect(user).not.toBeNull();
    expect(user?.email).toBe("alex.rivera@university.edu");
    expect(user?.onboarding_completed_at).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("stays logged out after logout until explicit demo entry", async () => {
    const client = new ApiClient("http://localhost:8000");
    endDemoSession();
    expect(await client.getCurrentUser()).toBeNull();

    activateDemoSession();
    expect(await client.getCurrentUser()).not.toBeNull();
    await client.logout();
    expect(await client.getCurrentUser()).toBeNull();
  });

  it("returns distinct pages of jobs and reports the unsliced total", async () => {
    const client = new ApiClient("http://localhost:8000");
    const first = await client.listJobs({ page: 1, page_size: 2 });
    const second = await client.listJobs({ page: 2, page_size: 2 });
    expect(first.items).toHaveLength(2);
    expect(second.items).toHaveLength(2);
    expect(first.total).toBeGreaterThan(2);
    expect(first.items[0].id).not.toBe(second.items[0].id);
  });

  it("serves real-company jobs, dynamic fit analysis, resume alignment, skill gaps, improvement plan, tailoring draft, and review without backend calls", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new ApiClient("http://localhost:8000");
    activateDemoSession();

    const jobsResponse = await client.listJobs({ keyword: "AMD" });
    expect(jobsResponse.total).toBeGreaterThanOrEqual(1);
    const amdJob = jobsResponse.items[0];
    expect(amdJob.company_name).toBe("AMD");

    const fit = await client.getJobFit(amdJob.id);
    expect(fit.job_id).toBe(amdJob.id);
    expect((fit.matched ?? []).length).toBeGreaterThan(0);

    const resumes = await client.listResumes();
    expect(resumes.length).toBeGreaterThanOrEqual(2);
    const versions = await client.listResumeVersions(resumes[0].id);
    expect(versions.length).toBeGreaterThanOrEqual(1);
    const primaryVersionId = versions[0].id;

    const alignment = await client.getJobResumeAlignment(amdJob.id, primaryVersionId);
    expect(alignment.resume_version_id).toBe(primaryVersionId);
    expect((alignment.shown_on_resume ?? []).length).toBeGreaterThan(0);

    const gaps = await client.getJobSkillGaps(amdJob.id, primaryVersionId);
    expect(gaps.resume_version_id).toBe(primaryVersionId);

    const plan = await client.getResumeImprovementPlan(amdJob.id, primaryVersionId);
    expect(plan.resume_version_id).toBe(primaryVersionId);

    const draft = await client.getResumeTailoringDraft(amdJob.id, primaryVersionId);
    expect(draft.resume_version_id).toBe(primaryVersionId);
    expect((draft.keep ?? []).length).toBeGreaterThan(0);

    const review = await client.getResumeTailoringReview(amdJob.id, primaryVersionId);
    const items = review.items ?? [];
    expect(items.length).toBeGreaterThan(0);

    const updatedReview = await client.updateResumeTailoringReviewItem(
      amdJob.id,
      review.id,
      items[0].id,
      {
        decision: "ACCEPTED",
        user_edited_text: "Built Python and FastAPI microservices with automated CI/CD checks.",
      }
    );
    expect(updatedReview.items?.[0]?.decision).toBe("ACCEPTED");

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("persists application status updates, skill additions, and candidate profile assembly", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new ApiClient("http://localhost:8000");
    activateDemoSession();

    const apps = await client.listApplications();
    expect(apps.length).toBeGreaterThanOrEqual(4);

    const updatedApp = await client.updateApplication(apps[0].id, {
      expected_version: apps[0].version,
      status: "OFFER",
      notes: "Received internship offer call!",
    });
    expect(updatedApp.current_status).toBe("OFFER");

    const currentSkills = await client.getSkills();
    const updatedSkills = await client.replaceSkills({
      skill_ids: currentSkills.skill_ids ?? [],
      custom_values: [...(currentSkills.custom_values ?? []), "Kubernetes"],
    });
    expect(updatedSkills.custom_values).toContain("Kubernetes");

    const candidateProfile = await client.getCandidateProfile();
    expect(candidateProfile.profile?.legal_first_name).toBe("Alex");
    expect(candidateProfile.custom_skills?.some((s) => s.name === "Kubernetes")).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
