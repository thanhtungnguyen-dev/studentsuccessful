import { describe, expect, it } from "vitest";
import { changedEducationFields, degreeLevels, educationFormValues, educationPayload, studyYears } from "./form";

const form = { ...educationFormValues(), institution_name: "University of Calgary", degree_level: "BS", major: "CS", study_year: "YEAR_3", start_date: "2024-09-01", expected_grad_month: "6", expected_grad_year: "2028" };

describe("Education form facts and final edit payload", () => {
  it("starts with no inferred facts, scale, or primary selection", () => {
    const initial = educationFormValues();
    expect(initial.degree_level).toBe(""); expect(initial.gpa_scale).toBe("");
    expect(initial.is_primary).toBe(false); expect(initial.gpa_include_on_apps).toBe(false);
  });
  it("uses exactly the approved structured choices", () => {
    expect(degreeLevels).toEqual(["BS", "BA", "MS", "PHD", "ASSOCIATES", "OTHER"]);
    expect(studyYears).toEqual(["YEAR_1", "YEAR_2", "YEAR_3", "YEAR_4", "YEAR_5_PLUS", "GRADUATE", "OTHER"]);
    expect(() => educationPayload({ ...form, degree_level: "BACHELOR" })).toThrow("Select");
    expect(() => educationPayload({ ...form, study_year: "First" })).toThrow("Select");
  });
  it.each([["3.54", "4.00"], ["4.20", "4.33"], ["10.00", "10.00"], ["85.00", "100.00"], ["100.00", "100.00"]])("preserves exact decimal text %s / %s", (value, scale) => {
    const payload = educationPayload({ ...form, gpa_value: value, gpa_scale: scale });
    expect(payload.gpa_value).toBe(value); expect(payload.gpa_scale).toBe(scale);
  });
  it.each([["3.54", ""], ["", "4.00"], ["3.541", "4.00"], ["4.01", "4.00"], ["-1", "4.00"], ["0", "0"], ["1000", "1000"]])("rejects invalid pair %s / %s", (value, scale) => {
    expect(() => educationPayload({ ...form, gpa_value: value, gpa_scale: scale })).toThrow();
  });
  it("requires disclosure to be disabled when clearing GPA", () => {
    const original = { ...form, gpa_value: "3.54", gpa_scale: "4.00", gpa_include_on_apps: true };
    expect(() => changedEducationFields(original, { ...original, gpa_value: "", gpa_scale: "" })).toThrow("Disable GPA inclusion");
    expect(changedEducationFields(original, { ...original, gpa_value: "", gpa_scale: "", gpa_include_on_apps: false })).toEqual({ gpa_value: null, gpa_scale: null, gpa_include_on_apps: false });
  });
  it("sends one changed field and explicit optional clear without defaults", () => {
    const original = { ...form, minor: "Art" };
    expect(changedEducationFields(original, { ...original, major: " Physics " })).toEqual({ major: "Physics" });
    expect(changedEducationFields(original, { ...original, minor: " " })).toEqual({ minor: null });
    expect(changedEducationFields(original, { ...original, is_primary: true })).toEqual({ is_primary: true });
  });
  it("compares graduation at month precision", () => {
    expect(educationPayload({ ...form, start_date: "2028-06-30" }).start_date).toBe("2028-06-30");
    expect(() => educationPayload({ ...form, start_date: "2028-07-01" })).toThrow("Graduation cannot precede");
  });
});
