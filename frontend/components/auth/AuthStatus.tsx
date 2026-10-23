"use client";
import { LoadingState } from "../ui/LoadingState";
import { Dashboard } from "../dashboard/Dashboard";
import { InteractiveLanding } from "../landing/InteractiveLanding";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
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
            Review applications, resumes, and the experience you've saved.
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
      {user && !sessionError && !completed && (
        <section className="ui-card setup-card" aria-labelledby="setup-title">
          <div>
            <p className="eyebrow">PROFILE SETUP</p>
            <h2 id="setup-title">Finish your profile</h2>
            <p className="muted">Review your information before using the workspace.</p>
          </div>
          <Link className="primary" href="/onboarding/review">
            Continue setup <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </section>
      )}
      {completed && user && <Dashboard key={user.id} />}
    </main>
  );
}
