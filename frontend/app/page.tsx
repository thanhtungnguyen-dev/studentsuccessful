"use client";

import { AuthStatus } from "../components/auth/AuthStatus";
import { InteractiveLanding } from "../components/landing/InteractiveLanding";
import { isDemoModeEnabled } from "../lib/demo/config";

export default function HomePage() {
  if (isDemoModeEnabled()) {
    return <InteractiveLanding />;
  }
  return <AuthStatus />;
}
