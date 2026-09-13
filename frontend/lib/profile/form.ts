import type { Profile, ProfileUpdate } from "../api/client";

type Field = { key: keyof ProfileUpdate; label: string; maxLength: number; required?: boolean; type?: "tel" | "url"; multiline?: boolean; help?: string };
export const profileSections: { title: string; fields: Field[] }[] = [
  { title: "Identity", fields: [
    { key: "legal_first_name", label: "Legal first name", maxLength: 100, required: true },
    { key: "legal_middle_name", label: "Legal middle name", maxLength: 100 },
    { key: "legal_last_name", label: "Legal last name", maxLength: 100, required: true },
    { key: "preferred_name", label: "Preferred name", maxLength: 100 },
  ] },
  { title: "Contact", fields: [
    { key: "phone_number", label: "Phone", maxLength: 30, type: "tel", help: "5–20 digits; country code, dialing punctuation and extension are welcome." },
  ] },
  { title: "Address", fields: [
    { key: "address_street", label: "Street address (lines 1 and 2)", maxLength: 255, multiline: true },
    { key: "address_city", label: "City", maxLength: 100 },
    { key: "address_state_province", label: "Province / state / region", maxLength: 100 },
    { key: "address_postal_code", label: "Postal code", maxLength: 30 },
    { key: "address_country_code", label: "Country code", maxLength: 2, help: "Enter your two-letter country code, for example CA. We do not infer it." },
  ] },
  { title: "Professional links", fields: [
    { key: "linkedin_url", label: "LinkedIn", maxLength: 500, type: "url" },
    { key: "github_url", label: "GitHub", maxLength: 500, type: "url" },
    { key: "portfolio_url", label: "Portfolio / personal website", maxLength: 500, type: "url" },
  ] },
];
export type ProfileFormValues = Record<keyof ProfileUpdate, string>;

export function profileFormValues(profile: Profile | null): ProfileFormValues {
  return Object.fromEntries(profileSections.flatMap((section) => section.fields)
    .map(({ key }) => [key, profile?.[key] ?? ""])) as ProfileFormValues;
}

export function changedProfileFields(previous: ProfileFormValues, next: ProfileFormValues): ProfileUpdate {
  const changes: ProfileUpdate = {};
  for (const { fields } of profileSections) {
    for (const { key, required } of fields) {
      const value = next[key].trim();
      if (value === previous[key].trim()) continue;
      if (key === "legal_first_name" || key === "legal_last_name") changes[key] = value;
      else changes[key] = required ? value : value || null;
    }
  }
  return changes;
}
