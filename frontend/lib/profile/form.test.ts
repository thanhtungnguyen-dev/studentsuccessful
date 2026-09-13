import { describe, expect, it } from "vitest";
import { changedProfileFields, profileFormValues } from "./form";

describe("profile partial form payload", () => {
  it("starts with no inferred facts", () => {
    expect(Object.values(profileFormValues(null)).every((value) => value === "")).toBe(true);
  });
  it("sends only edited fields, with null for an explicitly cleared optional value", () => {
    const original = profileFormValues({ legal_first_name: "Anne", legal_last_name: "李", preferred_name: "Annie", address_city: "Calgary" });
    expect(changedProfileFields(original, { ...original, preferred_name: "  " })).toEqual({ preferred_name: null });
    expect(changedProfileFields(original, { ...original, address_city: " Montréal " })).toEqual({ address_city: "Montréal" });
    expect(changedProfileFields(original, { ...original, legal_first_name: " Anne " })).toEqual({});
  });
  it("creates only submitted facts and preserves multiline street addresses", () => {
    const original = profileFormValues(null);
    expect(changedProfileFields(original, { ...original, legal_first_name: "李", legal_last_name: "Anne", address_street: "12 Main\nUnit 4" })).toEqual({
      legal_first_name: "李", legal_last_name: "Anne", address_street: "12 Main\nUnit 4",
    });
  });
});
