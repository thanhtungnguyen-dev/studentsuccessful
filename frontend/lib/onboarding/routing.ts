import type { CurrentUser } from "../api/client";

export function postAuthDestination(user: CurrentUser): "/" | "/onboarding/review" {
  return user.onboarding_completed_at ? "/" : "/onboarding/review";
}
