/**
 * Frontend Demo Mode configuration.
 *
 * Enable via `NEXT_PUBLIC_DEMO_MODE=true`.
 * When enabled, the application runs 100% in the browser using realistic sample student data
 * persisted in localStorage, without requiring FastAPI or PostgreSQL.
 */

export function isDemoModeEnabled(): boolean {
  if (typeof process !== "undefined" && process.env) {
    const nextFlag = process.env.NEXT_PUBLIC_DEMO_MODE;
    if (nextFlag === "true" || nextFlag === "1") {
      return true;
    }
  }
  return false;
}

export const DEMO_STORAGE_KEY = "studentsuccessful_demo_workspace_v2";
export const DEMO_API_STORAGE_KEY = "studentsuccessful_demo_api_state_v2";
export const DEMO_SESSION_STORAGE_KEY = "studentsuccessful_demo_authenticated_v1";
