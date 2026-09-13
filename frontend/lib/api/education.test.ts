import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, type Education, type EducationCreate } from "./client";

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const payload: EducationCreate = { institution_name: "University of Calgary", degree_level: "BS", major: "CS", study_year: "YEAR_3", start_date: "2024-09-01", expected_grad_month: 6, expected_grad_year: 2028, gpa_value: "100.00", gpa_scale: "100.00", is_primary: false, gpa_include_on_apps: false };
const record: Education = { ...payload, gpa_value: "100.00", gpa_scale: "100.00", id: "record-id", created_at: "2026-09-05T00:00:00Z", updated_at: "2026-09-05T00:00:00Z" };
function respond(status: number, body: unknown) {
  const json = vi.fn().mockResolvedValue(body);
  const fetch = vi.fn().mockResolvedValue({ ok: status >= 200 && status < 300, status, json });
  vi.stubGlobal("fetch", fetch); return { fetch, json };
}

describe("approved Education client", () => {
  it.each([{ body: [] }, { body: [record] }])("lists the generated collection on the approved same-origin path", async ({ body }) => {
    const { fetch } = respond(200, body);
    expect(await new ApiClient("http://backend:8000").listEducation()).toEqual(body);
    expect(fetch).toHaveBeenCalledWith("/api/v1/profile/education", expect.objectContaining({ method: "GET", credentials: "same-origin", cache: "no-store", headers: {}, signal: expect.any(AbortSignal) }));
  });
  it("reads a fresh CSRF cookie separately for create, update and delete", async () => {
    const { fetch } = respond(201, record);
    const browser = { cookie: "ss_csrf=first" }; vi.stubGlobal("document", browser);
    const client = new ApiClient();
    expect(await client.createEducation(payload)).toEqual(record);
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/education", expect.objectContaining({ method: "POST", body: JSON.stringify(payload), headers: { "Content-Type": "application/json", "X-CSRF-Token": "first" }, credentials: "same-origin", cache: "no-store" }));
    browser.cookie = "ss_csrf=second";
    await client.updateEducation(record.id, { minor: null });
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/education/record-id", expect.objectContaining({ method: "PATCH", body: '{"minor":null}', headers: { "Content-Type": "application/json", "X-CSRF-Token": "second" }, credentials: "same-origin", cache: "no-store" }));
    browser.cookie = "ss_csrf=third";
    const json = vi.fn(); fetch.mockResolvedValue({ ok: true, status: 204, json });
    expect(await client.deleteEducation(record.id)).toBeUndefined();
    expect(fetch).toHaveBeenLastCalledWith("/api/v1/profile/education/record-id", expect.objectContaining({ method: "DELETE", headers: { "X-CSRF-Token": "third" }, credentials: "same-origin", cache: "no-store" }));
    expect(fetch.mock.calls.at(-1)?.[1]).not.toHaveProperty("body");
    expect(json).not.toHaveBeenCalled();
  });
  it.each(["create", "update", "delete"])("refuses %s without CSRF", async (method) => {
    const { fetch } = respond(200, record); vi.stubGlobal("document", { cookie: "" });
    const client = new ApiClient();
    await expect(method === "create" ? client.createEducation(payload) : method === "update" ? client.updateEducation(record.id, {}) : client.deleteEducation(record.id)).rejects.toMatchObject({ status: 403 });
    expect(fetch).not.toHaveBeenCalled();
  });
  it.each([401, 403, 404, 422, 500])("handles HTTP %s without exposing server detail", async (status) => {
    respond(status, { detail: "SECRET exception" }); vi.stubGlobal("document", { cookie: "ss_csrf=token" });
    const client = new ApiClient();
    for (const operation of [() => client.listEducation(), () => client.createEducation(payload), () => client.updateEducation(record.id, {}), () => client.deleteEducation(record.id)]) {
      await expect(operation()).rejects.toMatchObject({ status, message: expect.not.stringContaining("SECRET") });
    }
  });
  it("handles unavailable backend and malformed JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("internal")));
    await expect(new ApiClient().listEducation()).rejects.toMatchObject({ status: 0 });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, json: () => { throw new Error("internal"); } }));
    await expect(new ApiClient().listEducation()).rejects.toThrow("Unexpected response");
  });
});
