import type { Education, EducationCreate, EducationUpdate } from "../api/client";

export const degreeLevels = ["BS", "BA", "MS", "PHD", "ASSOCIATES", "OTHER"] as const satisfies readonly EducationCreate["degree_level"][];
export const studyYears = ["YEAR_1", "YEAR_2", "YEAR_3", "YEAR_4", "YEAR_5_PLUS", "GRADUATE", "OTHER"] as const satisfies readonly EducationCreate["study_year"][];
export const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export type EducationFormValues = Record<Exclude<keyof EducationCreate, "is_primary" | "gpa_include_on_apps">, string> & { is_primary: boolean; gpa_include_on_apps: boolean };

export function educationFormValues(record?: Education): EducationFormValues {
  return {
    institution_name: record?.institution_name ?? "", degree_level: record?.degree_level ?? "",
    major: record?.major ?? "", minor: record?.minor ?? "", study_year: record?.study_year ?? "",
    start_date: record?.start_date ?? "", expected_grad_month: record ? String(record.expected_grad_month) : "",
    expected_grad_year: record ? String(record.expected_grad_year) : "", gpa_value: record?.gpa_value ?? "",
    gpa_scale: record?.gpa_scale ?? "", gpa_include_on_apps: record?.gpa_include_on_apps ?? false,
    is_primary: record?.is_primary ?? false,
  };
}

// Exact integer hundredths for comparison; submitted GPA remains a decimal string.
function hundredths(value: string): bigint | null {
  if (!/^\d{1,3}(?:\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * BigInt(100) + BigInt(fraction.padEnd(2, "0"));
}

export function educationPayload(values: EducationFormValues): EducationCreate {
  if (!values.institution_name.trim() || !values.major.trim()) throw new Error("Enter the institution and major.");
  const degree = degreeLevels.find((value) => value === values.degree_level);
  const study = studyYears.find((value) => value === values.study_year);
  if (!degree || !study) throw new Error("Select a degree level and study year.");
  const month = Number(values.expected_grad_month), year = Number(values.expected_grad_year);
  if (!Number.isInteger(month) || month < 1 || month > 12 || !Number.isInteger(year) || year < 2000 || year > 2100) throw new Error("Choose a graduation month and a year from 2000 to 2100.");
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.start_date)) throw new Error("Enter the actual start date.");
  const [startYear, startMonth] = values.start_date.split("-").map(Number);
  if (startYear > year || (startYear === year && startMonth > month)) throw new Error("Graduation cannot precede the start month/year.");
  const value = values.gpa_value.trim(), scale = values.gpa_scale.trim();
  if (Boolean(value) !== Boolean(scale)) throw new Error("Enter both GPA value and scale, or clear both.");
  if (values.gpa_include_on_apps && !value) throw new Error("Disable GPA inclusion when clearing GPA, or supply a complete GPA pair.");
  if (value) {
    const v = hundredths(value), s = hundredths(scale);
    if (v === null || s === null || s <= BigInt(0) || v > s) throw new Error("Use GPA value / positive native scale, value no greater than scale, with at most two decimal places and three integer digits.");
  }
  return {
    institution_name: values.institution_name.trim(), degree_level: degree, major: values.major.trim(),
    minor: values.minor.trim() || null, study_year: study, start_date: values.start_date,
    expected_grad_month: month, expected_grad_year: year, gpa_value: value || null, gpa_scale: scale || null,
    gpa_include_on_apps: values.gpa_include_on_apps, is_primary: values.is_primary,
  };
}

export function changedEducationFields(original: EducationFormValues, next: EducationFormValues): EducationUpdate {
  const before = educationPayload(original), after = educationPayload(next);
  return Object.fromEntries(Object.entries(after).filter(([key, value]) => value !== before[key as keyof EducationCreate])) as EducationUpdate;
}
