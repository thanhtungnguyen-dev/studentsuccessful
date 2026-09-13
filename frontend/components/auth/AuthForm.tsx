"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { apiClient, authErrorMessage } from "../../lib/api/client";
import { postAuthDestination } from "../../lib/onboarding/routing";
import { useAuth } from "./AuthProvider";

export function AuthForm({ mode }: { mode: "register" | "login" }) {
  const registering = mode === "register";
  const title = registering ? "Register" : "Login";
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

  return <main className="auth-shell">
    <Link href="/" className="brand">StudentSuccessful</Link>
    <section className="auth-card" aria-labelledby="form-title">
      <h1 id="form-title">{title}</h1>
      <p className="muted">{registering ? "Create your account." : "Welcome back. Sign in to your account."}</p>
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
          <button type="submit" className="primary">{busy ? "Please wait…" : title}</button>
        </fieldset>
      </form>
      <p className="auth-footer">{registering ? "Already have an account? " : "New here? "}<Link href={registering ? "/login" : "/register"}>{registering ? "Login" : "Register"}</Link></p>
    </section>
  </main>;
}
