"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, type ReactNode } from "react";
import { House, BriefcaseBusiness, ClipboardList, ContactRound, UserRound, GraduationCap, Building2, Globe2, SlidersHorizontal, ListChecks, FolderOpen, Files, Link2, Menu, X, ArrowUpRight } from "lucide-react";
import { AccountControls } from "../auth/AccountControls";
import { useAuth } from "../auth/AuthProvider";

const primary = [
  { href: "/", label: "Home", icon: House },
  { href: "/jobs", label: "Jobs", icon: BriefcaseBusiness },
  { href: "/applications", label: "Applications", icon: ClipboardList },
  { href: "/candidate", label: "Candidate Profile", icon: ContactRound },
];
const profile = [
  { href: "/profile", label: "Personal Information", icon: UserRound },
  { href: "/education", label: "Education", icon: GraduationCap },
  { href: "/employment", label: "Employment", icon: Building2 },
  { href: "/work-authorization", label: "Work Authorization", icon: Globe2 },
  { href: "/preferences", label: "Career Preferences", icon: SlidersHorizontal },
  { href: "/skills", label: "Skills", icon: ListChecks },
  { href: "/projects", label: "Projects", icon: FolderOpen },
  { href: "/resumes", label: "Resumes", icon: Files },
  { href: "/artifacts", label: "Career Artifacts", icon: Link2 },
];

export function WorkspaceNavigation({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const links = (items: typeof primary) => items.map(({ href, label, icon: Icon }) => {
    const active = href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
    return <Link key={href} href={href} aria-current={active ? "page" : undefined} onClick={onNavigate}><Icon size={18} aria-hidden="true" /><span>{label}</span></Link>;
  });
  return <nav aria-label="Workspace" className="workspace-nav">
    <p className="nav-caption">Main</p><div className="nav-group">{links(primary)}</div>
    <p className="nav-caption">Profile</p>
    <div className="nav-group">{links(profile.slice(0,5))}</div><p className="nav-caption">Portfolio</p><div className="nav-group">{links(profile.slice(5))}</div>
    <p className="nav-caption">Job Tools</p><div className="nav-utilities"><Link href="/jobs?view=saved" onClick={onNavigate}>Saved Searches<ArrowUpRight size={14} aria-hidden="true" /></Link><Link href="/alerts" onClick={onNavigate}>Alerts<ArrowUpRight size={14} aria-hidden="true" /></Link></div>
  </nav>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, error } = useAuth();
  const pathname = usePathname();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { dialog.current?.close(); trigger.current?.focus(); };
  if (!user || error || pathname === "/login" || pathname === "/register") return children;
  const brand = <Link className="workspace-brand" href="/"><span className="brand-monogram" aria-hidden="true">S</span>StudentSuccessful</Link>;
  return <div className="workspace">
    <a className="skip-link" href="#workspace-content">Skip to content</a>
    <aside className="desktop-sidebar">{brand}<WorkspaceNavigation pathname={pathname} /><div className="sidebar-account"><AccountControls desktopMenu /></div></aside>
    <header className="mobile-topbar">{brand}<button ref={trigger} className="icon-button" aria-label="Open navigation" aria-haspopup="dialog" onClick={() => dialog.current?.showModal()}><Menu size={22} aria-hidden="true" /></button></header>
    <dialog ref={dialog} className="navigation-sheet" aria-labelledby="navigation-title" onClose={() => trigger.current?.focus()} onClick={event => { if (event.target === event.currentTarget) close(); }} onKeyDown={event => {
      if (event.key !== "Tab") return;
      const controls = event.currentTarget.querySelectorAll<HTMLElement>('a[href], button:not(:disabled)');
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }}>
      <div className="sheet-content"><div className="sheet-heading"><h2 id="navigation-title">Navigation</h2><button className="icon-button" aria-label="Close navigation" onClick={close}><X size={22} aria-hidden="true" /></button></div><WorkspaceNavigation pathname={pathname} onNavigate={close} /></div>
    </dialog>
    <div id="workspace-content" className="workspace-content" tabIndex={-1}>{children}</div>
  </div>;
}
