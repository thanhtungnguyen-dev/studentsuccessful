import { apiClient, ApiError, type CurrentUser } from "../api/client";

export const REVIEW_PATH = "/onboarding/review";
export const REVIEW_SECTIONS = [
  { key: "profile", title: "Application Profile", href: "/profile" },
  { key: "education", title: "Education", href: "/education" },
  { key: "employment", title: "Employment", href: "/employment" },
  { key: "authorization", title: "Work Authorization", href: "/work-authorization" },
  { key: "preferences", title: "Career Preferences", href: "/preferences" },
] as const;

export async function loadReview() {
  const [profile, education, employment, authorization, preferences, roles, inactiveRoles, industries, locations, companies, skills] = await Promise.all([
    apiClient.getProfile(), apiClient.listEducation(), apiClient.listEmployment(), apiClient.listWorkAuthorizations(), apiClient.getPreferences(),
    apiClient.listRoles(), apiClient.listRoles({ active: false }), apiClient.listIndustries(), apiClient.listLocations(), apiClient.listCompanies(), apiClient.listSkills(),
  ]);
  return { profile, education, employment, authorization, preferences,
    catalogs: { role_ids: [...roles, ...inactiveRoles], industry_ids: industries, location_ids: locations.map(row => ({ id: row.id, name: [row.city, row.state_province, row.country_code].filter(Boolean).join(", ") })), company_ids: companies, skill_ids: skills } };
}
export type ReviewData = Awaited<ReturnType<typeof loadReview>>;

// Persistence and the refreshed server session must both confirm completion.
export function reviewCompletion(checkSession: () => Promise<CurrentUser | null>, goHome: () => void) {
  let started = false;
  return async () => {
    if (started) return;
    started = true;
    try {
      const completed = await apiClient.completeOnboarding();
      if (!completed.onboarding_completed_at) throw new ApiError(500, "Completion could not be confirmed. Please try again.");
      const current = await checkSession();
      if (!current) throw new ApiError(401, "Please log in again before completing onboarding.");
      if (!current.onboarding_completed_at) throw new ApiError(500, "Completion could not be confirmed. Please try again.");
      goHome();
    } catch (error) { started = false; throw error; }
  };
}
