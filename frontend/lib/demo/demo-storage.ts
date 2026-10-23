import { DEMO_STORAGE_KEY } from "./config";
import { createInitialDemoState, DemoWorkspaceState } from "./mock-data";

let memoryFallbackState: DemoWorkspaceState | null = null;

export function loadDemoState(): DemoWorkspaceState {
  if (typeof window === "undefined") {
    return memoryFallbackState ?? createInitialDemoState();
  }

  try {
    const raw = window.localStorage.getItem(DEMO_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<DemoWorkspaceState>;
      const initial = createInitialDemoState();
      return {
        profile: { ...initial.profile, ...(parsed.profile ?? {}) },
        resumes:
          Array.isArray(parsed.resumes) && parsed.resumes.length > 0
            ? parsed.resumes
            : initial.resumes,
        activeResumeId:
          parsed.activeResumeId === "v1" || parsed.activeResumeId === "v2"
            ? parsed.activeResumeId
            : initial.activeResumeId,
        savedJobIds: Array.isArray(parsed.savedJobIds)
          ? parsed.savedJobIds
          : initial.savedJobIds,
        selectedJobId:
          typeof parsed.selectedJobId === "string"
            ? parsed.selectedJobId
            : initial.selectedJobId,
        applications: Array.isArray(parsed.applications)
          ? parsed.applications
          : initial.applications,
      };
    }
  } catch {
    if (memoryFallbackState) return memoryFallbackState;
  }

  const fresh = createInitialDemoState();
  saveDemoState(fresh);
  return fresh;
}

export function saveDemoState(state: DemoWorkspaceState): void {
  memoryFallbackState = state;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Ignore storage quota or private-browsing write errors
  }
}

export function resetDemoState(): DemoWorkspaceState {
  const initial = createInitialDemoState();
  memoryFallbackState = initial;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(DEMO_STORAGE_KEY);
      window.localStorage.setItem(DEMO_STORAGE_KEY, JSON.stringify(initial));
    } catch {
      // Ignore storage errors
    }
  }
  return initial;
}
