import { afterEach, expect, it, vi } from "vitest";
import { apiClient, ApiError, type CurrentUser } from "../api/client";
import { loadReview, reviewCompletion, REVIEW_SECTIONS } from "./review";
afterEach(() => vi.restoreAllMocks());
const user = { id: "owner", email: "owner@example.com", onboarding_completed_at: "2026-09-07T12:00:00Z" } as CurrentUser;
function reads() {
  vi.spyOn(apiClient, "getProfile").mockResolvedValue(null);
  vi.spyOn(apiClient, "listEducation").mockResolvedValue([]);
  vi.spyOn(apiClient, "listEmployment").mockResolvedValue([]);
  vi.spyOn(apiClient, "listWorkAuthorizations").mockResolvedValue([]);
  vi.spyOn(apiClient, "getPreferences").mockResolvedValue({ custom_values: [{ preference_type: "SKILL", value: "Rust interest" }] });
  vi.spyOn(apiClient, "listRoles").mockResolvedValue([]);
  vi.spyOn(apiClient, "listIndustries").mockResolvedValue([]);
  vi.spyOn(apiClient, "listLocations").mockResolvedValue([{ id: "place", country_code: "CA", state_province: "Alberta", city: "Calgary" }]);
  vi.spyOn(apiClient, "listCompanies").mockResolvedValue([]);
  vi.spyOn(apiClient, "listSkills").mockResolvedValue([]);
}
it("loads existing saved APIs without writing or inferring preferences", async () => {
  reads(); const put = vi.spyOn(apiClient, "replacePreferences");
  const result = await loadReview();
  expect(result.profile).toBeNull(); expect(result.education).toEqual([]);
  expect(result.preferences.custom_values).toEqual([{ preference_type: "SKILL", value: "Rust interest" }]);
  expect(result.catalogs.location_ids).toEqual([{ id: "place", name: "Calgary, Alberta, CA" }]);
  expect(apiClient.listRoles).toHaveBeenCalledWith({ active: false });expect(put).not.toHaveBeenCalled();
});
it("reloads current saved values after editing, without relying on client storage", async () => {
  reads(); await loadReview();
  vi.mocked(apiClient.getProfile).mockResolvedValue({ legal_first_name: "Updated", legal_last_name: "Name" });
  expect((await loadReview()).profile?.legal_first_name).toBe("Updated");expect(apiClient.getProfile).toHaveBeenCalledTimes(2);
});
it.each([401, 500])("does not represent an API %s failure as empty saved data", async status => {
  reads();vi.mocked(apiClient.listEmployment).mockRejectedValue(new ApiError(status, "Load failed"));
  await expect(loadReview()).rejects.toMatchObject({ status });
});
it("routes every Edit action to its existing data page", () => {
  expect(REVIEW_SECTIONS.map(x => x.href)).toEqual(["/profile", "/education", "/employment", "/work-authorization", "/preferences"]);
});
it("completion occurs only after activation and safely ignores duplicates", async () => {
  let resolve!: (value: CurrentUser) => void;
  const check = vi.fn(() => new Promise<CurrentUser>(done => { resolve = done; })), navigate = vi.fn();
  vi.spyOn(apiClient, "completeOnboarding").mockResolvedValue(user);
  const complete = reviewCompletion(check, navigate);
  expect(check).not.toHaveBeenCalled();expect(navigate).not.toHaveBeenCalled();
  const first = complete(), duplicate = complete();await Promise.resolve();expect(check).toHaveBeenCalledTimes(1);expect(navigate).not.toHaveBeenCalled();
  resolve(user);await Promise.all([first, duplicate]);await complete();expect(navigate).toHaveBeenCalledTimes(1);
});
it("failed completion preserves state and can be retried", async () => {
  const check = vi.fn<() => Promise<CurrentUser | null>>().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(user), navigate = vi.fn();
  vi.spyOn(apiClient, "completeOnboarding").mockResolvedValue(user);
  const complete = reviewCompletion(check, navigate);await expect(complete()).rejects.toThrow("offline");expect(navigate).not.toHaveBeenCalled();
  await complete();expect(navigate).toHaveBeenCalledTimes(1);
});
it("does not complete with an expired session", async () => {
  vi.spyOn(apiClient, "completeOnboarding").mockResolvedValue(user);
  const navigate = vi.fn();await expect(reviewCompletion(async () => null, navigate)()).rejects.toMatchObject({ status: 401 });expect(navigate).not.toHaveBeenCalled();
});

it("waits for persisted completion before refreshing or navigating and guards rapid activation", async () => {
  let resolve!: (value: CurrentUser) => void;
  const persist = vi.spyOn(apiClient, "completeOnboarding").mockImplementation(() => new Promise(done => { resolve = done; }));
  const refresh = vi.fn().mockResolvedValue(user), navigate = vi.fn();
  const finish = reviewCompletion(refresh, navigate);
  expect(persist).not.toHaveBeenCalled();
  const pending = finish(); await finish();
  expect(persist).toHaveBeenCalledTimes(1); expect(refresh).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  resolve(user); await pending;
  expect(refresh).toHaveBeenCalledTimes(1); expect(navigate).toHaveBeenCalledTimes(1);
});
it("failed persistence never refreshes or navigates and permits a real retry", async () => {
  const persist = vi.spyOn(apiClient, "completeOnboarding").mockRejectedValueOnce(new ApiError(503, "Please try again.")).mockResolvedValue(user);
  const refresh = vi.fn().mockResolvedValue(user), navigate = vi.fn(); const finish = reviewCompletion(refresh, navigate);
  await expect(finish()).rejects.toThrow("Please try again.");
  expect(refresh).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
  await finish(); expect(persist).toHaveBeenCalledTimes(2); expect(navigate).toHaveBeenCalledTimes(1);
});
it("does not navigate when refreshed backend session still reports incomplete", async () => {
  vi.spyOn(apiClient, "completeOnboarding").mockResolvedValue(user);
  const navigate = vi.fn();
  await expect(reviewCompletion(async () => ({...user, onboarding_completed_at: null}), navigate)()).rejects.toThrow("Completion could not be confirmed");
  expect(navigate).not.toHaveBeenCalled();
});
it("rejects a successful response that does not confirm persistence", async () => {
  vi.spyOn(apiClient, "completeOnboarding").mockResolvedValue({...user, onboarding_completed_at: null});
  const refresh = vi.fn(), navigate = vi.fn();
  await expect(reviewCompletion(refresh, navigate)()).rejects.toThrow("Completion could not be confirmed");
  expect(refresh).not.toHaveBeenCalled(); expect(navigate).not.toHaveBeenCalled();
});
