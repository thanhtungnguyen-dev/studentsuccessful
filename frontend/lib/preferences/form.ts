import type { Preferences } from "../api/client";
export const GROUPS = [
  { key: "role_ids", type: "ROLE", label: "Roles" },
  { key: "industry_ids", type: "INDUSTRY", label: "Industries" },
  { key: "location_ids", type: "LOCATION", label: "Locations" },
  { key: "company_ids", type: "COMPANY", label: "Companies" },
  { key: "skill_ids", type: "SKILL", label: "Technology interests" },
] as const;
export const WORK_MODES = ["ON_SITE", "HYBRID", "REMOTE"] as const satisfies NonNullable<Preferences["work_modes"]>;
export const EMPLOYMENT_TYPES = ["INTERNSHIP", "CO_OP", "NEW_GRAD", "PART_TIME"] as const satisfies NonNullable<Preferences["employment_types"]>;
export function completePreferences(value: Preferences = {}): Required<Preferences> {
  return { role_ids: value.role_ids ?? [], industry_ids: value.industry_ids ?? [], location_ids: value.location_ids ?? [], company_ids: value.company_ids ?? [], skill_ids: value.skill_ids ?? [], work_modes: value.work_modes ?? [], employment_types: value.employment_types ?? [], custom_values: value.custom_values ?? [] };
}
export function toggleSelection<T>(selected: T[], value: T): T[] { return selected.includes(value) ? selected.filter(item => item !== value) : [...selected, value]; }
export function addCustom(value: Preferences, preference_type: NonNullable<Preferences["custom_values"]>[number]["preference_type"], display: string): Required<Preferences> {
  const state = completePreferences(value), normalize = (s: string) => s.trim().replace(/\s+/g, " ").toLowerCase();
  if (!display.trim() || display.length > 150) throw new Error("Enter a custom value of 1–150 characters.");
  if (state.custom_values.some(item => item.preference_type === preference_type && normalize(item.value) === normalize(display))) throw new Error("This custom value is already selected.");
  return { ...state, custom_values: [...state.custom_values, { preference_type, value: display }] };
}
