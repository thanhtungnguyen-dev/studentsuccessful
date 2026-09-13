import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, type Profile } from "./client";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const profile: Profile = { legal_first_name: "Anne", legal_last_name: "李", preferred_name: "Annie" };
function respond(status: number, body: unknown) {
  const fetch = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetch); return fetch;
}

describe("Application Profile client", () => {
  it.each([profile, null])("reads the generated response with same-origin authentication", async (body) => {
    const fetch = respond(200, body);
    expect(await new ApiClient("http://backend:8000").getProfile()).toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/v1/profile", expect.objectContaining({
      method: "GET", credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal),
    }));
  });
  it("sends only supplied fields and reads the current CSRF cookie for every PATCH", async () => {
    const fetch = respond(200, profile);
    const browser = { cookie: "ss_csrf=first" }; vi.stubGlobal("document", browser);
    const client = new ApiClient();
    const payload = { preferred_name: null };
    expect(await client.updateProfile(payload)).toEqual(profile);
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile", expect.objectContaining({
      method: "PATCH", body: JSON.stringify(payload), credentials: "same-origin", cache: "no-store",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": "first" },
    }));
    browser.cookie = "ss_csrf=second";
    await client.updateProfile({ preferred_name: "New" });
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile", expect.objectContaining({
      headers: { "Content-Type": "application/json", "X-CSRF-Token": "second" },
    }));
  });
  it("refuses a mutation without a current cookie", async () => {
    const fetch = respond(200, profile); vi.stubGlobal("document", { cookie: "" });
    await expect(new ApiClient().updateProfile({ preferred_name: null })).rejects.toMatchObject({ status: 403 });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([401, 403, 422, 500])("keeps HTTP %s distinct from an absent profile and hides internals", async (status) => {
    respond(status, { detail: "SECRET traceback" }); vi.stubGlobal("document", { cookie: "ss_csrf=current" });
    const client = new ApiClient();
    await expect(client.getProfile()).rejects.toMatchObject({ status, message: expect.not.stringContaining("SECRET") });
    await expect(client.updateProfile({})).rejects.toMatchObject({ status, message: expect.not.stringContaining("SECRET") });
  });
  it("handles network failures and malformed success responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("private detail")));
    await expect(new ApiClient().getProfile()).rejects.toMatchObject({ status: 0 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => { throw new Error("private"); } }));
    await expect(new ApiClient().getProfile()).rejects.toThrow("Unexpected response");
  });
});
