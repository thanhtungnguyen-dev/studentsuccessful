"use client";
import { LoadingState } from "../ui/LoadingState";
import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "../ui/PageHeader";
import { useRouter } from "next/navigation";
import { useAuth } from "../auth/AuthProvider";
import { ApiError, authErrorMessage } from "../../lib/api/client";
import { loadReview, reviewCompletion, type ReviewData } from "../../lib/onboarding/review";
import { ReviewSections } from "./ReviewSections";

export function ReviewPage() {
  const { user, error, refresh } = useAuth();
  return <main className="auth-shell review-shell"><Link className="brand" href="/">StudentSuccessful</Link><PageHeader title="Onboarding Review" description="Review your saved information. Use Edit to make changes, save them, then return here." />
    {user === undefined ? error ? <><p role="alert" className="auth-error">{error}</p><button className="secondary" onClick={() => void refresh().catch(() => {})}>Retry session</button></> : <LoadingState label="Checking your session…" />
      : user === null ? <p>Please <Link href="/login">Login</Link> to review your information.</p> : <ReviewContent key={user.id} />}
  </main>;
}
function ReviewContent() {
  const { refresh } = useAuth(); const router = useRouter();
  const [data, setData] = useState<ReviewData | null>(null), [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0), [busy, setBusy] = useState(false);
  const finish = useMemo(() => reviewCompletion(refresh, () => router.replace("/")), [refresh, router]);
  useEffect(() => {
    let active = true; setData(null); setError("");
    loadReview().then(result => { if (active) setData(result); }).catch(error => {
      if (active) { setError(authErrorMessage(error)); if (error instanceof ApiError && error.status === 401) void refresh().catch(() => {}); }
    });
    return () => { active = false; };
  }, [attempt, refresh]);
  async function complete() {
    if (!data || busy) return;
    setBusy(true); setError("");
    try { await finish(); } catch(error) { setError(authErrorMessage(error)); setBusy(false); }
  }
  return <>
    {!data && !error && <LoadingState label="Loading saved onboarding information…" />}
    {error && <div><p className="auth-error" role="alert">{error}</p>{!data && <button className="secondary" onClick={() => setAttempt(x => x + 1)}>Retry review</button>}</div>}
    {data && <ReviewSections data={data} />}
    <div className="review-finish"><p className="muted">Complete onboarding to save your completion and return home. Your saved information remains available to edit.</p>
      <button className="primary" disabled={!data || busy} onClick={() => void complete()}>{busy ? "Completing…" : "Complete onboarding"}</button>
    </div>
  </>;
}
