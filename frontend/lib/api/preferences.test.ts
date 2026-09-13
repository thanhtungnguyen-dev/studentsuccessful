import { afterEach, expect, it, vi } from "vitest";
import { ApiClient, type Preferences } from "./client";
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function mock(status = 200, body: unknown = {}) {
  const fetch = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetch); return fetch;
}
it("loads and replaces the complete aggregate with current CSRF on every PUT", async () => {
  const payload: Preferences = { role_ids: ["role-a", "role-b"], work_modes: ["REMOTE"], custom_values: [{ preference_type: "SKILL", value: "Rust" }] };
  const fetch = mock(200, payload), browser = { cookie: "ss_csrf=one" };vi.stubGlobal("document", browser);
  const client = new ApiClient("http://backend:8000");
  expect(await client.getPreferences()).toEqual(payload);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/preferences", expect.objectContaining({ method: "GET", headers: {}, cache: "no-store", credentials: "same-origin" }));
  await client.replacePreferences(payload);
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/preferences", expect.objectContaining({ method: "PUT", headers: { "X-CSRF-Token": "one", "Content-Type": "application/json" }, body: JSON.stringify(payload), cache: "no-store", credentials: "same-origin" }));
  browser.cookie = "ss_csrf=two";await client.replacePreferences({});
  expect(fetch).toHaveBeenLastCalledWith("/api/v1/preferences", expect.objectContaining({ method: "PUT", body: "{}", headers: { "X-CSRF-Token": "two", "Content-Type": "application/json" } }));
});
it("does not issue PUT without CSRF", async () => {
  const fetch = mock(); vi.stubGlobal("document", { cookie: "" });
  await expect(new ApiClient().replacePreferences({})).rejects.toMatchObject({ status: 403 });expect(fetch).not.toHaveBeenCalled();
});
it("uses exact read-only catalog paths and documented encoded filters", async () => {
  const fetch = mock(200, []), client = new ApiClient();
  for (const [call, url] of [
    [() => client.listRoles({ q: "A & B", active: false }), "/api/v1/catalog/roles?q=A+%26+B&active=false"],
    [() => client.listSkills({ q: "Python", category: "LANGUAGE" }), "/api/v1/catalog/skills?q=Python&category=LANGUAGE"],
    [() => client.listIndustries(), "/api/v1/catalog/industries"],
    [() => client.listCompanies({ q: "Example" }), "/api/v1/catalog/companies?q=Example"],
    [() => client.listLocations({ country_code: "CA", q: "Calgary" }), "/api/v1/catalog/locations?country_code=CA&q=Calgary"],
  ] as const) {
    expect(await call()).toEqual([]);expect(fetch).toHaveBeenLastCalledWith(url, expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", headers: {} }));
  }
});
it.each([401, 403, 422, 500])("handles HTTP %s without exposing private error detail", async status => {
  mock(status, { detail: "SECRET" });vi.stubGlobal("document", { cookie: "ss_csrf=token" });const client = new ApiClient();
  for (const call of [() => client.getPreferences(), () => client.replacePreferences({}), () => client.listRoles()]) await expect(call()).rejects.toMatchObject({ status, message: expect.not.stringContaining("SECRET") });
});
it("handles network and malformed JSON safely", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("internal")));await expect(new ApiClient().getPreferences()).rejects.toMatchObject({ status: 0 });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => {throw new Error("internal");} }));await expect(new ApiClient().getPreferences()).rejects.toThrow("Unexpected response");
});
