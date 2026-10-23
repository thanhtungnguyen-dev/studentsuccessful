"use client";
import { LoadingState } from "../ui/LoadingState";
import { Dashboard } from "../dashboard/Dashboard";
import { InteractiveLanding } from "../landing/InteractiveLanding";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { AccountControls } from "./AccountControls";
import { useAuth } from "./AuthProvider";

export function AuthStatus() {
  const { user, error: sessionError, refresh } = useAuth();
  const completed = Boolean(user?.onboarding_completed_at) && !sessionError;

  if (user === null && !sessionError) {
    return <InteractiveLanding />;
  }

  if (sessionError) {
    return (
      <>
        <InteractiveLanding />
        <div role="alert" className="ssi-connection-warning">
          <span>{sessionError}</span>
          <button
            type="button"
            onClick={() => {
              void refresh().catch(() => {});
            }}
          >
            Try again
          </button>
        </div>
      </>
    );
  }

  return (
    <main className={`auth-shell${completed ? " dashboard-shell" : ""}`}>
      <section className="auth-card home-welcome" aria-labelledby="home-title">
        {completed && <p className="eyebrow">YOUR WORKSPACE</p>}
        <h1 id="home-title">{completed ? "Home" : "StudentSuccessful"}</h1>
        {completed && (
          <p className="muted">
            Your jobs, resumes, and applications in one place.
          </p>
        )}
        {user === undefined ? (
          <LoadingState label="Checking your session…" />
        ) : user ? (
          <>
            {!user.onboarding_completed_at && (
              <p>
                <Link className="secondary" href="/onboarding/review">
                  Continue onboarding
                </Link>
              </p>
            )}
            <div className="home-account mobile-account">
              <AccountControls />
            </div>
          </>
        ) : null}
      </section>
      {user && !sessionError && (
        <section
          className={`ui-card setup-card${completed ? " setup-complete" : ""}`}
          aria-labelledby="setup-title"
        >
          <div>
            {!completed && <p className="eyebrow">MAKE YOUR NEXT MOVE</p>}
            <h2 id="setup-title">Profile setup</h2>
            <p className="muted">
              {completed ? (
                <>
                  <Check size={15} aria-hidden="true" />
                  Complete
                </>
              ) : (
                "Review your information before you complete onboarding."
              )}
            </p>
          </div>
          <Link
            className={completed ? "secondary" : "primary"}
            href="/onboarding/review"
          >
            {completed ? "Review profile setup" : "Continue setup"}
            {completed && <ArrowRight size={16} aria-hidden="true" />}
          </Link>
        </section>
      )}
      {completed && user && <Dashboard key={user.id} />}
    </main>
  );
}
