"use client";

import Link from "next/link";
import { ArrowRight, Search, ChartNoAxesCombined, ListChecks } from "lucide-react";
import { Reveal } from "../ui/Reveal";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiClient, authErrorMessage } from "../../lib/api/client";
import { postAuthDestination } from "../../lib/onboarding/routing";
import { useAuth } from "./AuthProvider";

export function AuthForm({ mode }: { mode: "register" | "login" }) {
  const registering = mode === "register";
  const title = registering ? "Create account" : "Sign in";
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const { refresh } = useAuth();
  const router = useRouter();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    const password = String(data.get("password") ?? "");
    setError("");
    if (!email || !password || (registering && !data.get("confirmation"))) { setError("Please complete all fields."); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { setError("Please enter a valid email address."); return; }
    const length = Array.from(password).length;
    if (length < (registering ? 8 : 1) || length > 128) {
      setError(registering ? "Use a password between 8 and 128 characters." : "Password must be between 1 and 128 characters."); return;
    }
    if (registering && password !== data.get("confirmation")) { setError("Passwords do not match."); return; }
    setBusy(true);
    try {
      await apiClient[mode]({ email, password });
      // The response's user/CSRF fields never establish persistent client auth state.
      const user = await refresh();
      if (!user) { setError("Your session could not be confirmed. Please log in again."); return; }
      router.replace(postAuthDestination(user));
    } catch (error) { setError(authErrorMessage(error)); }
    finally { setBusy(false); }
  }

  return <main className="auth-layout">
    <aside className="auth-story">
      <Link href="/" className="workspace-brand"><span className="brand-monogram" aria-hidden="true">S</span>StudentSuccessful</Link>
      <Reveal className="auth-story-copy">
        <p className="eyebrow">YOUR NEXT CHAPTER STARTS HERE</p>
        <h2>Build your career<br />with clarity.</h2>
        <p>Discover opportunities, understand your fit, and stay organized throughout your job search.</p>
        <ul className="auth-benefits">
          <li><Search size={20} aria-hidden="true" />Discover relevant opportunities</li>
          <li><ChartNoAxesCombined size={20} aria-hidden="true" />Understand candidate-job fit</li>
          <li><ListChecks size={20} aria-hidden="true" />Track every application</li>
        </ul>
      </Reveal>
      <p className="auth-story-note">A thoughtful workspace for your next move.</p>
    </aside>
    <div className="auth-form-panel">
    <Link href="/" className="workspace-brand auth-mobile-brand"><span className="brand-monogram" aria-hidden="true">S</span>StudentSuccessful</Link>
    <Reveal as="section" className="auth-card auth-form-card" aria-labelledby="form-title">
      <p className="eyebrow">{registering ? "GET STARTED" : "GOOD TO SEE YOU AGAIN"}</p>
      <h1 id="form-title">{registering ? "Create your account" : "Welcome back"}</h1>
      <p className="muted">{registering ? "Bring your experience and opportunities together." : "Continue your career journey."}</p>
      <form onSubmit={submit} noValidate aria-busy={busy}>
        <fieldset disabled={busy}>
          <label htmlFor="email">Email</label>
          <input id="email" name="email" type="email" autoComplete="email" autoCapitalize="none" required />
          <label htmlFor="password">Password</label>
          <input id="password" name="password" type="password" autoComplete={registering ? "new-password" : "current-password"} required aria-describedby={registering ? "password-help" : undefined} />
          {registering && <>
            <p id="password-help" className="field-help">8–128 characters.</p>
            <label htmlFor="confirmation">Confirm password</label>
            <input id="confirmation" name="confirmation" type="password" autoComplete="new-password" required />
          </>}
          {error && <p role="alert" className="auth-error">{error}</p>}
          <button type="submit" className="primary">{busy ? "Please wait…" : <>{title}<ArrowRight size={17} aria-hidden="true" /></>}</button>
        </fieldset>
      </form>
      <p className="auth-footer">{registering ? "Already have an account? " : "New here? "}<Link href={registering ? "/login" : "/register"}>{registering ? "Sign in" : "Create an account"}</Link></p>
    </Reveal>
    <p className="auth-form-note">Your experience. Your goals. Your next step.</p>
    </div>
  </main>;
}
