"use client";
import Link from "next/link";
import { AccountMenu } from "./AccountMenu";
import { UserRound } from "lucide-react";
import { useState } from "react";
import { apiClient, ApiError, authErrorMessage } from "../../lib/api/client";
import { useAuth } from "./AuthProvider";
export function AccountControls({ desktopMenu = false }: { desktopMenu?: boolean }) {
  const { user, refresh } = useAuth();
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
  if (desktopMenu && user) return <AccountMenu email={user.email} busy={busy} error={error} logout={logout} />;
  return <><p className="signed-in"><UserRound className="account-avatar" size={18} aria-hidden="true" /><span className="account-identity"><span className="account-caption">Account</span><strong title={user?.email}>{user?.email}</strong></span></p><button className="secondary" onClick={logout} disabled={busy}>{busy ? "Logging out…" : "Logout"}</button>{error && <><p role="alert" className="auth-error">{error}</p><Link href="/login">Login again</Link></>}</>;

}
