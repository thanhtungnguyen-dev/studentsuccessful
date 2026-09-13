import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError, authErrorMessage } from "./client";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const user = { id: "test-user", email: "student@example.com", is_active: true, created_at: "2026-09-05T00:00:00Z" };
function respond(status: number, body: unknown) {
  const fetch = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json: async () => body });
  vi.stubGlobal("fetch", fetch); return fetch;
}
describe("typed same-origin auth client", () => {
  it.each(["register", "login"] as const)("%s sends only typed credentials and parses success", async (operation) => {
    const payload = { email: user.email, password: "Example-password-1" };
    const body = { user, csrf_token: "ignored-response-token" };
    const fetch = respond(operation === "register" ? 201 : 200, body);
    expect(await new ApiClient("http://backend:8000")[operation](payload)).toEqual(body);
    expect(fetch).toHaveBeenCalledWith(`/api/v1/auth/${operation}`, expect.objectContaining({
      method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json" },
      credentials: "same-origin", cache: "no-store", signal: expect.any(AbortSignal),
    }));
  });
  it("reads the current user with cookies and without caching", async () => {
    const fetch = respond(200, user);
    expect(await new ApiClient().getCurrentUser()).toEqual(user);
    expect(fetch).toHaveBeenCalledWith("/api/v1/auth/me", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store" }));
  });
  it("treats only a 401 me response as logged out", async () => {
    respond(401, {}); expect(await new ApiClient().getCurrentUser()).toBeNull();
    respond(503, {}); await expect(new ApiClient().getCurrentUser()).rejects.toBeInstanceOf(ApiError);
  });
  it("reads the CURRENT cookie for every logout, ignoring auth JSON", async () => {
    const fetch = respond(200, { user, csrf_token: "not-authoritative" });
    const client = new ApiClient();
    await client.login({ email: user.email, password: "password" });
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ message: "Successfully logged out" }) });
    const browser = { cookie: "ss_csrf=first" }; vi.stubGlobal("document", browser);
    expect(await client.logout()).toEqual({ message: "Successfully logged out" });
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/auth/logout", expect.objectContaining({ method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": "first" } }));
    browser.cookie = "ss_csrf=second";
    await client.logout();
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/auth/logout", expect.objectContaining({ headers: { "X-CSRF-Token": "second" } }));
  });
  it("refuses logout without CSRF rather than sending an unprotected mutation", async () => {
    const fetch = respond(200, {}); vi.stubGlobal("document", { cookie: "" });
    await expect(new ApiClient().logout()).rejects.toMatchObject({ status: 403 }); expect(fetch).not.toHaveBeenCalled();
  });
  it.each([401, 403, 409, 422, 500, 502])("maps HTTP %s errors without exposing server detail", async (status) => {
    respond(status, { detail: "SECRET database traceback", code: "internal_exception" });
    await expect(new ApiClient().login({ email: user.email, password: "wrong" })).rejects.toMatchObject({ status });
    try { await new ApiClient().login({ email: user.email, password: "wrong" }); }
    catch (error) { expect(authErrorMessage(error)).not.toMatch(/SECRET|traceback|internal_exception/); }
  });
  it("uses generic invalid credentials for login", async () => {
    respond(401, { detail: "user missing" });
    await expect(new ApiClient().login({ email: user.email, password: "wrong" })).rejects.toThrow("Invalid email or password.");
  });
  it("explains duplicate registration", async () => {
    respond(409, {});
    await expect(new ApiClient().register({ email: user.email, password: "password" })).rejects.toThrow("An account with this email already exists.");
  });
  it("handles unreachable backend safely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("internal network detail")));
    await expect(new ApiClient().getCurrentUser()).rejects.toThrow("Unable to reach StudentSuccessful.");
  });
  it("handles invalid success JSON safely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => { throw new Error("bad JSON"); } }));
    await expect(new ApiClient().getCurrentUser()).rejects.toThrow("Unexpected response.");
  });
});
