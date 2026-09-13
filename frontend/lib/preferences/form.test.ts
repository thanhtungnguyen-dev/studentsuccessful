import { expect, it } from "vitest";
import { addCustom, completePreferences, toggleSelection, WORK_MODES, EMPLOYMENT_TYPES } from "./form";
it("builds a deterministic complete empty replacement", () => {
  expect(completePreferences()).toEqual({ role_ids: [], industry_ids: [], location_ids: [], company_ids: [], skill_ids: [], work_modes: [], employment_types: [], custom_values: [] });
});
it("multi-select adds and removes only the requested selection", () => {
  expect(toggleSelection(["a"], "b")).toEqual(["a", "b"]);expect(toggleSelection(["a", "b"], "a")).toEqual(["b"]);
});
it("keeps saved canonical IDs and explicit custom display values separate", () => {
  const value = addCustom({ skill_ids: ["python-id"] }, "SKILL", "  Python  ");
  expect(value.skill_ids).toEqual(["python-id"]);expect(value.custom_values).toEqual([{ preference_type: "SKILL", value: "  Python  " }]);
});
it.each(["My Role", " my  ROLE ", "MY\tROLE"])("rejects normalized duplicate %s", value => {
  expect(() => addCustom(addCustom({}, "ROLE", "My Role"), "ROLE", value)).toThrow("already selected");
});
it("allows matching custom names for different categories", () => {
  expect(addCustom(addCustom({}, "ROLE", "Example"), "COMPANY", "Example").custom_values).toHaveLength(2);
});
it.each(["", "  ", "x".repeat(151)])("rejects blank or oversized custom values", value => {
  expect(() => addCustom({}, "ROLE", value)).toThrow();
});
it("sends complete replacement after removal and reloads exactly saved selections", () => {
  const original = completePreferences({ role_ids: ["a", "b"], skill_ids: ["skill"], work_modes: ["REMOTE"] });
  const replacement = completePreferences({ ...original, role_ids: toggleSelection(original.role_ids, "a"), skill_ids: [] });
  expect(replacement.role_ids).toEqual(["b"]);expect(replacement.skill_ids).toEqual([]);expect(completePreferences(JSON.parse(JSON.stringify(replacement)))).toEqual(replacement);
});
it("uses only approved structured choices", () => {
  expect(WORK_MODES).toEqual(["ON_SITE", "HYBRID", "REMOTE"]);expect(EMPLOYMENT_TYPES).toEqual(["INTERNSHIP", "CO_OP", "NEW_GRAD", "PART_TIME"]);
});
