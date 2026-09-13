import {loadSkills,loadProjects} from "../portfolio/form";
import { apiClient, ApiError } from "../api/client";

async function loadPreferences() {
  const [preferences, ...catalogs] = await Promise.allSettled([
    apiClient.getPreferences(), apiClient.listRoles(), apiClient.listRoles({ active: false }),
    apiClient.listIndustries(), apiClient.listLocations(), apiClient.listCompanies(), apiClient.listSkills(),
  ] as const);
  if (preferences.status === "rejected") throw preferences.reason;
  // An expired session must still reach the existing authentication refresh path.
  for (const result of catalogs) if (result.status === "rejected" && result.reason instanceof ApiError && result.reason.status === 401) throw result.reason;
  const [roles, inactiveRoles, industries, locations, companies, skills] = catalogs;
  return { preferences: preferences.value, labelsUnavailable: catalogs.some(result => result.status === "rejected"), catalogs: {
    role_ids: [...(roles.status === "fulfilled" ? roles.value : []), ...(inactiveRoles.status === "fulfilled" ? inactiveRoles.value : [])],
    industry_ids: industries.status === "fulfilled" ? industries.value : [],
    location_ids: locations.status === "fulfilled" ? locations.value.map(row => ({id: row.id, name: [row.city, row.state_province, row.country_code].filter(Boolean).join(", ")})) : [],
    company_ids: companies.status === "fulfilled" ? companies.value : [],
    skill_ids: skills.status === "fulfilled" ? skills.value : [],
  }};
}
export type DashboardPreferences = Awaited<ReturnType<typeof loadPreferences>>;
export const dashboardLoaders = {
  artifacts: () => apiClient.listArtifacts(),
  resumes: () => apiClient.listResumes(),
  skills: loadSkills, projects: loadProjects,
  profile: () => apiClient.getProfile(),
  education: () => apiClient.listEducation(),
  employment: () => apiClient.listEmployment(),
  authorization: () => apiClient.listWorkAuthorizations(),
  preferences: loadPreferences,
};
