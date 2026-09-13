import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, type WorkAuthorization, type WorkAuthorizationCreate } from "./client";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const payload: WorkAuthorizationCreate = { country_code: "CA", authorization_status: "OTHER", requires_current_sponsorship: true, requires_future_sponsorship: false };
const record: WorkAuthorization = { ...payload, id: "record-id", last_confirmed_at: "2026-09-06T00:00:00Z", created_at: "2026-09-06T00:00:00Z", updated_at: "2026-09-06T00:00:00Z" };
function respond(status: number, body: unknown) {
  const json = vi.fn().mockResolvedValue(body);
  const fetch = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json });
  vi.stubGlobal("fetch", fetch); return { fetch, json };
}

describe("approved WorkAuthorization client", () => {
  it.each([{ body: [] }, { body: [record] }])("lists the generated collection on the approved same-origin path", async ({ body }) => {
    const { fetch } = respond(200, body);
    expect(await new ApiClient("http://backend:8000").listWorkAuthorizations()).toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/v1/profile/work-authorizations", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", headers: {}, signal: expect.any(AbortSignal) }));
  });
  it("reads a fresh CSRF cookie separately for create, update and delete", async () => {
    const { fetch } = respond(201, record);
    const browser = { cookie: "ss_csrf=first" }; vi.stubGlobal("document", browser);
    const client = new ApiClient();
    expect(await client.createWorkAuthorization(payload)).toEqual(record);
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/work-authorizations", expect.objectContaining({ method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json", "X-CSRF-Token": "first" }, credentials: "same-origin", cache: "no-store" }));
    browser.cookie = "ss_csrf=second";
    await client.updateWorkAuthorization(record.id, { notes: null });
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/work-authorizations/record-id", expect.objectContaining({ method: "PATCH", body: '{"notes":null}', headers: { "Content-Type": "application/json", "X-CSRF-Token": "second" }, credentials: "same-origin", cache: "no-store" }));
    browser.cookie = "ss_csrf=third";
    const json = vi.fn(); fetch.mockResolvedValue({ ok: true, status: 204, json });
    expect(await client.deleteWorkAuthorization(record.id)).toBeUndefined();
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/work-authorizations/record-id", expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "third" }, credentials: "same-origin", cache: "no-store" }));
    expect(fetch.mock.calls.at(-1)?.[1]).not.toHaveProperty("body");
    expect(json).not.toHaveBeenCalled();
  });
  it.each(["create", "update", "delete"])("refuses %s without CSRF", async (method) => {
    const { fetch } = respond(200, record); vi.stubGlobal("document", { cookie: "" });
    const client = new ApiClient();
    await expect(method === "create" ? client.createWorkAuthorization(payload) : method === "update" ? client.updateWorkAuthorization(record.id, {}) : client.deleteWorkAuthorization(record.id)).rejects.toMatchObject({ status: 403 });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([401, 403, 404, 409, 422, 500])("handles HTTP %s without exposing server detail", async (status) => {
    respond(status, { detail: "SECRET exception" }); vi.stubGlobal("document", { cookie: "ss_csrf=token" });
    const client = new ApiClient();
    for (const operation of [() => client.listWorkAuthorizations(), () => client.createWorkAuthorization(payload), () => client.updateWorkAuthorization(record.id, {}), () => client.deleteWorkAuthorization(record.id)]) {
      await expect(operation()).rejects.toMatchObject({ status, message: expect.not.stringContaining("SECRET") });
    }
  });
  it("handles unavailable backend and malformed JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("internal")));
    await expect(new ApiClient().listWorkAuthorizations()).rejects.toMatchObject({ status: 0 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => { throw new Error("internal"); } }));
    await expect(new ApiClient().listWorkAuthorizations()).rejects.toThrow("Unexpected response");
  });
});
