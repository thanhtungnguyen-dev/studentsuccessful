import type { Employment, EmploymentCreate, EmploymentUpdate } from "../api/client";

export type EmploymentFormValues = Record<Exclude<keyof EmploymentCreate, "currently_employed">, string> & { currently_employed: boolean };

export function employmentFormValues(record?: Employment): EmploymentFormValues {
  return { employer_name: record?.employer_name ?? "", job_title: record?.job_title ?? "", location: record?.location ?? "",
    start_date: record?.start_date ?? "", end_date: record?.end_date ?? "", currently_employed: record?.currently_employed ?? false,
    description: record?.description ?? "" };
}

export function employmentPayload(values: EmploymentFormValues): EmploymentCreate {
  if (!values.employer_name.trim() || !values.job_title.trim()) throw new Error("Enter an employer name and job title.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.start_date)) throw new Error("Enter the actual start date.");
  if (!values.currently_employed && !values.end_date) throw new Error("Enter an end date when not currently employed.");
  if (values.end_date && (!/^\d{4}-\d{2}-\d{2}$/.test(values.end_date) || values.end_date < values.start_date)) throw new Error("End date cannot precede start date.");
  return { employer_name: values.employer_name.trim(), job_title: values.job_title.trim(), location: values.location.trim() || null,
    start_date: values.start_date, end_date: values.end_date || null, currently_employed: values.currently_employed,
    description: values.description.trim() ? values.description : null };
}

export function changedEmploymentFields(original: EmploymentFormValues, next: EmploymentFormValues): EmploymentUpdate {
  const before = employmentPayload(original), after = employmentPayload(next);
  return Object.fromEntries(Object.entries(after).filter(([key, value]) => value !== before[key as keyof EmploymentCreate])) as EmploymentUpdate;
}
