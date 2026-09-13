import { describe, expect, it } from "vitest";
import { changedEmploymentFields, employmentFormValues, employmentPayload } from "./form";

const form = { ...employmentFormValues(), employer_name: "Employer", job_title: "Developer", start_date: "2026-01-01", currently_employed: true };

describe("employment factual form", () => {
  it("starts without inferred employer, location, dates or current status", () => {
    expect(employmentFormValues()).toEqual({ employer_name: "", job_title: "", location: "", start_date: "", end_date: "", currently_employed: false, description: "" });
  });
  it.each(["employer_name", "job_title", "start_date"] as const)("requires %s", (key) => {
    expect(() => employmentPayload({ ...form, [key]: "" })).toThrow();
  });
  it.each([true, false])("permits known end date with currently_employed=%s", (current) => {
    const result = employmentPayload({ ...form, currently_employed: current, end_date: "2027-05-01" });
    expect(result.end_date).toBe("2027-05-01"); expect(result.currently_employed).toBe(current);
  });
  it("permits a current role without end date but rejects a completed one", () => {
    expect(employmentPayload(form).end_date).toBeNull();
    expect(() => employmentPayload({ ...form, currently_employed: false })).toThrow("end date");
  });
  it("validates date order including merged edits, allowing equal dates", () => {
    const original = { ...form, end_date: "2026-08-31" };
    expect(() => changedEmploymentFields(original, { ...original, start_date: "2026-09-01" })).toThrow("precede");
    expect(() => employmentPayload({ ...form, end_date: "2025-12-31" })).toThrow("precede");
    expect(employmentPayload({ ...form, end_date: form.start_date }).end_date).toBe(form.start_date);
  });
  it("preserves end date when changing from completed to current", () => {
    const original = { ...form, currently_employed: false, end_date: "2027-05-01" };
    expect(changedEmploymentFields(original, { ...original, currently_employed: true })).toEqual({ currently_employed: true });
  });
  it("rejects clearing a completed role's end date unless becoming current", () => {
    const original = { ...form, currently_employed: false, end_date: "2026-08-31" };
    expect(() => changedEmploymentFields(original, { ...original, end_date: "" })).toThrow();
    expect(changedEmploymentFields(original, { ...original, end_date: "", currently_employed: true })).toEqual({ end_date: null, currently_employed: true });
  });
  it.each(["location", "description"] as const)("clears optional %s without overwriting other facts", (key) => {
    const original = { ...form, location: "Calgary", description: "Notes" };
    expect(changedEmploymentFields(original, { ...original, [key]: "  " })).toEqual({ [key]: null });
  });
  it("sends a single title edit and preserves description content", () => {
    const original = { ...form, description: "  User text\n  second line  " };
    expect(employmentPayload(original).description).toBe(original.description);
    expect(changedEmploymentFields(original, { ...original, job_title: " Engineer " })).toEqual({ job_title: "Engineer" });
  });
});
