"use client";

import Link from "next/link";
import { ChevronUp, LogOut, UserRound } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

type AccountActions = { email: string; busy: boolean; error: string; logout: () => void; close: () => void };
export function AccountMenuItems({ email, busy, error, logout, close }: AccountActions) {
  return <>
    <div className="account-menu-identity" role="presentation"><UserRound size={20} aria-hidden="true" /><span><span>Account</span><strong title={email}>{email}</strong></span></div>
    <Link role="menuitem" href="/profile" onClick={close}><UserRound size={16} aria-hidden="true" />Personal Information</Link>
    <button role="menuitem" type="button" onClick={logout} disabled={busy}><LogOut size={16} aria-hidden="true" />{busy ? "Logging out…" : "Logout"}</button>
    {error && <div className="account-menu-error"><p role="alert">{error}</p><Link role="menuitem" href="/login" onClick={close}>Login again</Link></div>}
  </>;
}

export function AccountMenu({ email, busy, error, logout }: Omit<AccountActions, "close">) {
  const [open, setOpen] = useState(false);
  const [bottom, setBottom] = useState(80);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  const close = () => { setOpen(false); trigger.current?.focus(); };
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !menu.current?.contains(event.target) && !trigger.current?.contains(event.target)) {
        event.preventDefault(); setOpen(false); trigger.current?.focus();
      }
    };
    const reposition = () => setBottom(window.innerHeight - (trigger.current?.getBoundingClientRect().top ?? 80) + 8);
    document.addEventListener("pointerdown", outside);
    window.addEventListener("resize", reposition);
    return () => { document.removeEventListener("pointerdown", outside); window.removeEventListener("resize", reposition); };
  }, [open]);
  return <div className="account-control">
    <button ref={trigger} className="account-trigger" type="button" aria-label={`Account menu for ${email}`} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => {
      setBottom(window.innerHeight - (trigger.current?.getBoundingClientRect().top ?? 80) + 8);
      setOpen(value => !value);
    }} onKeyDown={event => { if (event.key === "Escape" && open) { event.preventDefault(); close(); } }}>
      <UserRound className="identity-avatar" size={18} aria-hidden="true" />
      <span className="identity-copy"><strong title={email}>{email}</strong><span>Account</span></span>
      <ChevronUp className="account-caret" size={16} aria-hidden="true" />
    </button>
    {open && <div ref={menu} id={id} role="menu" aria-label="Account actions" className="account-menu" style={{bottom}} onBlur={event => {
      if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget) && event.relatedTarget !== trigger.current) setOpen(false);
    }} onKeyDown={event => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); return; }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]:not(:disabled)'));
      const index = items.indexOf(document.activeElement as HTMLElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }}><AccountMenuItems email={email} busy={busy} error={error} logout={logout} close={close} /></div>}
  </div>;
}
