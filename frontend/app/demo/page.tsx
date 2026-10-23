"use client";

import { useEffect, useRef } from "react";
import { notFound, useRouter } from "next/navigation";
import { activateDemoSession } from "../../lib/demo/demo-store";
import { isDemoModeEnabled } from "../../lib/demo/config";
import { useAuth } from "../../components/auth/AuthProvider";
import { AuthStatus } from "../../components/auth/AuthStatus";

export default function DemoWorkspacePage() {
  const { user, refresh } = useAuth();
  const router = useRouter();
  const demoEnabled = isDemoModeEnabled();
  const hasEntered = useRef(false);

  useEffect(() => {
    if (!demoEnabled || hasEntered.current) return;
    hasEntered.current = true;
    activateDemoSession();
    const params = new URLSearchParams(window.location.search);
    const tab = params.get("tab");
    const subRoute =
      tab === "jobs"
        ? "/jobs"
        : tab === "fit"
          ? "/jobs/amd-sw/fit"
          : tab === "resumes"
            ? "/resumes"
            : tab === "tracker"
              ? "/applications"
              : tab === "profile"
                ? "/candidate"
                : null;

    if (!user) {
      void refresh()
        .catch(() => {})
        .finally(() => {
          if (subRoute) router.replace(subRoute);
        });
    } else if (subRoute) {
      router.replace(subRoute);
    }
  }, [demoEnabled, refresh, router, user]);

  if (!demoEnabled) notFound();
  return <AuthStatus />;
}
