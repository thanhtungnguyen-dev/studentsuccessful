import type { WorkAuthorization, WorkAuthorizationCreate, WorkAuthorizationUpdate } from "../api/client";

export const STATUS_LABELS = {
  CITIZEN: "Citizen",
  PERMANENT_RESIDENT: "Permanent resident",
  STUDENT_WORK_AUTHORIZATION: "Student work authorization",
  TEMPORARY_WORK_AUTHORIZATION: "Temporary work authorization",
  OTHER: "Other",
  STUDENT_VISA_CPT_OPT: "Student visa CPT/OPT (US-specific legacy category)",
  WORK_VISA: "Work visa (legacy category)",
} satisfies Record<WorkAuthorizationCreate["authorization_status"], string>;
export type WorkAuthorizationFormValues = {
  country_code: string;
  authorization_status: WorkAuthorizationCreate["authorization_status"] | "";
  requires_current_sponsorship: "" | "yes" | "no";
  requires_future_sponsorship: "" | "yes" | "no";
  notes: string;
};
export function workAuthorizationFormValues(record?: WorkAuthorization): WorkAuthorizationFormValues {
  return { country_code: record?.country_code ?? "", authorization_status: record?.authorization_status ?? "",
    requires_current_sponsorship: record ? (record.requires_current_sponsorship ? "yes" : "no") : "",
    requires_future_sponsorship: record ? (record.requires_future_sponsorship ? "yes" : "no") : "", notes: record?.notes ?? "" };
}
export function workAuthorizationPayload(values: WorkAuthorizationFormValues): WorkAuthorizationCreate {
  const country = values.country_code.trim();
  if (!/^[A-Za-z]{2}$/.test(country)) throw new Error("Enter exactly two ASCII letters for the country code.");
  if (!values.authorization_status || !Object.hasOwn(STATUS_LABELS, values.authorization_status)) throw new Error("Select an authorization status explicitly.");
  if (!["yes", "no"].includes(values.requires_current_sponsorship) || !["yes", "no"].includes(values.requires_future_sponsorship)) throw new Error("Answer both sponsorship questions explicitly.");
  if (values.notes.trim().length > 255) throw new Error("Notes must be at most 255 characters.");
  return { country_code: country.toUpperCase(), authorization_status: values.authorization_status,
    requires_current_sponsorship: values.requires_current_sponsorship === "yes", requires_future_sponsorship: values.requires_future_sponsorship === "yes", notes: values.notes.trim() || null };
}
export function changedWorkAuthorizationFields(original: WorkAuthorizationFormValues, next: WorkAuthorizationFormValues): WorkAuthorizationUpdate {
  const before = workAuthorizationPayload(original), after = workAuthorizationPayload(next);
  return Object.fromEntries(Object.entries(after).filter(([key, value]) => value !== before[key as keyof WorkAuthorizationCreate])) as WorkAuthorizationUpdate;
}
