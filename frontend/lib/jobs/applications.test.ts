import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import { ApplicationCard } from "../../components/applications/ApplicationsPage";
import { MarkAsApplied } from "../../components/applications/MarkAsApplied";
import { ApiClient, type Application } from "../api/client";
import { safeApplicationUrl } from "./applicationUrl";

const application: Application = {
  id: "application-one",
  canonical_job_id: "job-one",
  job_title: "Software Engineer Intern",
  company_name: "Example Co",
  application_url: "https://apply.example/job-one",
  job_lifecycle: "CLOSED",
  current_status: "INTERVIEW",
  resume_version_id: "resume-version-one",
  resume_title: "Internship Resume",
  resume_version_number: 3,
  applied_at: "2026-09-11T12:00:00Z",
  notes: "Recruiter screen Sep 18",
  version: 2,
  created_at: "2026-09-11T12:00:00Z",
  updated_at: "2026-09-12T12:00:00Z",
  history: [
    { id: "history-one", previous_status: null, new_status: "APPLIED", notes: null, transitioned_at: "2026-09-11T12:00:00Z" },
    { id: "history-two", previous_status: "APPLIED", new_status: "INTERVIEW", notes: "Recruiter screen Sep 18", transitioned_at: "2026-09-12T12:00:00Z" },
  ],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("uses one safe HTTP(S) guard for canonical Apply destinations", () => {
  expect(safeApplicationUrl("https://apply.example/path")).toBe("https://apply.example/path");
  for (const value of ["javascript:alert(1)", "data:text/html,hi", "https://user@example.test", "https://apply.example/a b", "https:\\\\apply.example"]) {
    expect(safeApplicationUrl(value)).toBeNull();
  }
});

it("renders an explicit manual confirmation instead of treating Apply as submitted", () => {
  const html = render(h(MarkAsApplied, { canonicalJobId: "job-one", jobTitle: "Software Engineer Intern" }));
  expect(html).toContain("Mark as Applied");
  expect(html).not.toContain("Tracked: Applied");
});

it("renders private manual status history and a closed listing without changing the application", () => {
  const html = render(h(ApplicationCard, {
    application,
    pending: false,
    onStatus: vi.fn(),
    onSaveNotes: vi.fn(),
  }));
  for (const text of [
    "Software Engineer Intern",
    "Example Co",
    "Status: Interview",
    "Internship Resume · v3",
    "Closed listing; tracking remains active.",
    "Applied → Interview",
    "Recruiter screen Sep 18",
    "Apply",
  ]) {
    expect(html).toContain(text);
  }
  expect(html).toContain('href="https://apply.example/job-one"');
});

it("uses no-store authenticated application reads and CSRF-protected create and update calls", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ items: [application] }) })
    .mockResolvedValueOnce({ ok: true, status: 201, json: async () => application })
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ ...application, current_status: "OFFER", version: 3 }) });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("document", { cookie: "ss_csrf=current" });
  const client = new ApiClient();

  await client.listApplications("INTERVIEW");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/applications?status=INTERVIEW",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }),
  );
  await client.createApplication({ canonical_job_id: "job one", notes: "Submitted" });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/applications",
    expect.objectContaining({
      method: "POST",
      headers: { "X-CSRF-Token": "current", "Content-Type": "application/json" },
      body: '{"canonical_job_id":"job one","notes":"Submitted"}',
      credentials: "same-origin",
      cache: "no-store",
    }),
  );
  await client.updateApplication("application one", { expected_version: 2, status: "OFFER" });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/applications/application%20one",
    expect.objectContaining({
      method: "PATCH",
      headers: { "X-CSRF-Token": "current", "Content-Type": "application/json" },
      body: '{"expected_version":2,"status":"OFFER"}',
      credentials: "same-origin",
      cache: "no-store",
    }),
  );
});
