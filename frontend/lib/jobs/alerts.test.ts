import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";

import { AlertInbox, AlertsPage } from "../../components/alerts/AlertsPage";
import { ApiClient, type CurrentUser, type JobAlertInbox } from "../api/client";

const authState = vi.hoisted(() => ({
  user: undefined as CurrentUser | null | undefined,
  error: "",
}));
vi.mock("../../components/auth/AuthProvider", () => ({
  useAuth: () => ({ ...authState, refresh: vi.fn() }),
}));

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  authState.user = undefined;
  authState.error = "";
});

const inbox: JobAlertInbox = {
  unread_count: 2,
  items: [
    {
      id: "instant-alert",
      canonical_job_id: "job-instant",
      saved_search_id: "search-instant",
      saved_search_name: "Canada Backend Internships",
      delivery_mode: "INSTANT",
      scheduled_for: "2026-09-11T10:00:00Z",
      created_at: "2026-09-11T10:00:00Z",
      delivered_at: "2026-09-11T10:00:01Z",
      read_at: null,
      title: "Backend Internship",
      company_name: "Example Co",
      employment_type: "INTERNSHIP",
      work_mode: "HYBRID",
      application_url: "https://apply.example/instant",
      first_seen_at: "2026-09-11T10:00:00Z",
      locations: ["Toronto, ON"],
    },
    {
      id: "hourly-first",
      canonical_job_id: "job-hourly-first",
      saved_search_id: "search-hourly",
      saved_search_name: "Hourly Software Internships",
      delivery_mode: "HOURLY_DIGEST",
      scheduled_for: "2026-09-11T11:00:00Z",
      created_at: "2026-09-11T10:10:00Z",
      delivered_at: "2026-09-11T11:00:00Z",
      read_at: null,
      title: "Platform Internship",
      company_name: "Example Co",
      employment_type: "INTERNSHIP",
      work_mode: "REMOTE",
      application_url: "https://apply.example/hourly-first",
      first_seen_at: "2026-09-11T10:10:00Z",
      locations: ["Remote"],
    },
    {
      id: "hourly-second",
      canonical_job_id: "job-hourly-second",
      saved_search_id: "search-hourly",
      saved_search_name: "Hourly Software Internships",
      delivery_mode: "HOURLY_DIGEST",
      scheduled_for: "2026-09-11T11:00:00Z",
      created_at: "2026-09-11T10:11:00Z",
      delivered_at: "2026-09-11T11:00:00Z",
      read_at: "2026-09-11T11:02:00Z",
      title: "Systems Internship",
      company_name: "Example Co",
      employment_type: "INTERNSHIP",
      work_mode: "HYBRID",
      application_url: "https://apply.example/hourly-second",
      first_seen_at: "2026-09-11T10:11:00Z",
      locations: ["Vancouver, BC"],
    },
  ],
};

it("renders private instant and grouped digest alerts with current canonical Apply links", () => {
  const html = render(h(AlertInbox, {
    inbox,
    pendingAlertIds: new Set<string>(),
    onView: vi.fn(),
    onMarkRead: vi.fn(),
  }));
  for (const text of [
    "2 unread",
    'New job matched &quot;Canada Backend Internships&quot;',
    'Hourly digest · new jobs matched &quot;Hourly Software Internships&quot;',
    "2 new canonical jobs",
    "Backend Internship",
    "Platform Internship",
    "Systems Internship",
    "Toronto, ON",
    "View",
    "Apply",
    "Mark read",
  ]) {
    expect(html).toContain(text);
  }
  expect(html).toContain('href="https://apply.example/instant"');
  expect(html).toContain('target="_blank"');
  expect(html).toContain('rel="noopener noreferrer"');
  expect(html).not.toMatch(/AI|recommend|application status|interview|offer/i);
});

it("renders the empty private inbox state", () => {
  const html = render(h(AlertInbox, {
    inbox: { items: [], unread_count: 0 },
    pendingAlertIds: new Set<string>(),
    onView: vi.fn(),
    onMarkRead: vi.fn(),
  }));
  expect(html).toContain("No delivered job alerts yet.");
  expect(html).toContain("Open saved searches");
});

it("uses no-store authenticated alert reads and CSRF-protected read mutations", async () => {
  const fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, status: 200, json: async () => inbox })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ id: "instant-alert", read_at: "2026-09-11T10:03:00Z" }),
    });
  vi.stubGlobal("fetch", fetch);
  vi.stubGlobal("document", { cookie: "ss_csrf=current" });
  const client = new ApiClient();
  await client.listAlerts();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/alerts",
    expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }),
  );
  await client.markAlertRead("instant alert");
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/alerts/instant%20alert",
    expect.objectContaining({
      method: "PATCH",
      headers: { "X-CSRF-Token": "current", "Content-Type": "application/json" },
      body: '{"read":true}',
      credentials: "same-origin",
      cache: "no-store",
    }),
  );
});

it("renders loading and signed-out states without another user's alert data", () => {
  authState.user = {
    id: "owner",
    email: "owner@example.com",
    is_active: true,
    created_at: "2026-09-11T10:00:00Z",
    onboarding_completed_at: "2026-09-11T10:00:00Z",
  };
  expect(render(h(AlertsPage))).toContain("Loading alerts…");
  authState.user = null;
  const signedOut = render(h(AlertsPage));
  expect(signedOut).toContain("Login");
  expect(signedOut).not.toContain("Backend Internship");
});
