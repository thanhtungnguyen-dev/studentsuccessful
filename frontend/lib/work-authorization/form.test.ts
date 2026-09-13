import { describe, expect, it } from "vitest";
import { STATUS_LABELS, changedWorkAuthorizationFields, workAuthorizationFormValues, workAuthorizationPayload, type WorkAuthorizationFormValues } from "./form";
const facts: WorkAuthorizationFormValues = { country_code: "ca", authorization_status: "OTHER", requires_current_sponsorship: "yes", requires_future_sponsorship: "no", notes: " Notes " };

describe("explicit authorization facts", () => {
  it("does not preselect status or sponsorship", () => {
    expect(workAuthorizationFormValues()).toEqual({ country_code: "", authorization_status: "", requires_current_sponsorship: "", requires_future_sponsorship: "", notes: "" });
  });
  it.each(["C", "CAN", "1A", "éA", "ß", ""])("rejects malformed country %s", (country_code) => {
    expect(() => workAuthorizationPayload({ ...facts, country_code })).toThrow("two ASCII letters");
  });
  it("normalizes lowercase and surrounding whitespace", () => {
    expect(workAuthorizationPayload({ ...facts, country_code: " ca " })).toMatchObject({ country_code: "CA", notes: "Notes" });
  });
  it.each(["authorization_status", "requires_current_sponsorship", "requires_future_sponsorship"] as const)("requires explicit %s", (key) => {
    expect(() => workAuthorizationPayload({ ...facts, [key]: "" })).toThrow();
  });
  it.each(Object.keys(STATUS_LABELS) as Array<keyof typeof STATUS_LABELS>)("does not infer sponsorship from %s", (authorization_status) => {
    expect(workAuthorizationPayload({ ...facts, authorization_status })).toMatchObject({ authorization_status, requires_current_sponsorship: true, requires_future_sponsorship: false });
    expect(workAuthorizationPayload({ ...facts, authorization_status, requires_current_sponsorship: "no", requires_future_sponsorship: "yes" })).toMatchObject({ authorization_status, requires_current_sponsorship: false, requires_future_sponsorship: true });
  });
  it.each(["", "   "])("clears blank notes", (notes) => {
    expect(changedWorkAuthorizationFields(facts, { ...facts, notes })).toEqual({ notes: null });
  });
  it("rejects notes over the limit", () => {
    expect(() => workAuthorizationPayload({ ...facts, notes: "x".repeat(256) })).toThrow("255");
  });
  it("submits only the changed sponsorship field and never timestamps", () => {
    expect(changedWorkAuthorizationFields(facts, { ...facts, requires_future_sponsorship: "yes" })).toEqual({ requires_future_sponsorship: true });
    expect(changedWorkAuthorizationFields(facts, { ...facts, country_code: "CA" })).toEqual({});
  });
});
