"use client";

import { Dashboard } from "../dashboard/Dashboard";
import Link from "next/link";
import { useState } from "react";
import { apiClient, ApiError, authErrorMessage } from "../../lib/api/client";
import { useAuth } from "./AuthProvider";

export function AuthStatus() {
  const { user, error: sessionError, refresh } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function logout() {
    setBusy(true); setError("");
    try {
      try { await apiClient.logout(); }
      catch (error) { if (!(error instanceof ApiError && error.status === 401)) throw error; }
      await refresh();
    } catch (error) { setError(authErrorMessage(error)); }
    finally { setBusy(false); }
  }
  const completed = Boolean(user?.onboarding_completed_at) && !sessionError;
  return <main className={`auth-shell${completed ? " dashboard-shell" : ""}`}>
    <section className="auth-card" aria-labelledby="home-title">
      {completed && <p className="brand">StudentSuccessful</p>}
      <h1 id="home-title">{completed ? "Home" : "StudentSuccessful"}</h1>
      {completed && <p className="muted">Your saved information, with quick access to your editors.</p>}
      {sessionError ? <>
        <p role="alert" className="auth-error">{sessionError}</p>
        <button className="primary" onClick={() => { void refresh().catch(() => {}); }}>Try again</button>
      </> : user === undefined ? <p role="status">Checking your session…</p> : user ? <>
        {!user.onboarding_completed_at && <p><Link className="secondary" href="/onboarding/review">Continue onboarding</Link></p>}
        <p className="signed-in">Signed in as <strong>{user.email}</strong></p>
        <nav aria-label="Primary" className="auth-footer"><Link href="/jobs">Jobs</Link> &middot; <Link href="/jobs?view=saved">Saved Searches</Link> &middot; <Link href="/alerts">Alerts</Link> &middot; <Link href="/applications">Applications</Link> &middot; <Link href="/profile">Profile</Link></nav>
        <p className="auth-footer muted">More: <Link href="/candidate">Candidate Profile</Link> &middot; <Link href="/education">Education</Link> &middot; <Link href="/employment">Employment</Link> &middot; <Link href="/work-authorization">Work Authorization</Link> &middot; <Link href="/preferences">Career Preferences</Link> &middot; <Link href="/skills">Skills</Link> &middot; <Link href="/projects">Projects</Link> &middot; <Link href="/artifacts">Career Artifacts</Link> &middot; <Link href="/onboarding/review">Onboarding Review</Link></p>
        <button className="primary" onClick={logout} disabled={busy}>{busy ? "Logging out…" : "Logout"}</button>
        {error && <><p role="alert" className="auth-error">{error}</p><Link href="/login">Login again</Link></>}
      </> : <>
        <p className="muted">Welcome. Create an account or sign in.</p>
        <nav aria-label="Account" className="auth-actions"><Link className="primary" href="/register">Register</Link><Link className="secondary" href="/login">Login</Link></nav>
      </>}
    </section>
    {completed && user && <Dashboard key={user.id} />}
  </main>;
}
