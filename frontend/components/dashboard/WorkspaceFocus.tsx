"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, BriefcaseBusiness, ClipboardList, FileText, CalendarCheck2, UserRound } from "lucide-react";
import { apiClient, type Application } from "../../lib/api/client";
import { CompanyLogo } from "../jobs/CompanyLogo";

const statusLabels: Record<string, string> = {
  APPLIED: "Applied", INTERVIEW: "Interview", OFFER: "Offer",
  REJECTED: "Not selected", WITHDRAWN: "Withdrawn",
};

export function WorkspaceFocus() {
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [resumeCount, setResumeCount] = useState<number | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoadError(false);
    Promise.allSettled([apiClient.listApplications(), apiClient.listResumes()])
      .then(([apps, resumes]) => {
        if (!active) return;
        setApplications(apps.status === "fulfilled" ? apps.value : null);
        setResumeCount(resumes.status === "fulfilled" ? resumes.value.length : null);
        setLoadError(apps.status === "rejected" || resumes.status === "rejected");
      });
    return () => { active = false; };
  }, [attempt]);

  const orderedApplications = applications === null ? null : [...applications].sort((a, b) => {
    const first = Date.parse(a.applied_at ?? "") || 0;
    const second = Date.parse(b.applied_at ?? "") || 0;
    return second - first;
  });
  const interviewCount = applications?.filter(item => item.current_status === "INTERVIEW").length ?? 0;
  const tracked = applications?.length ?? 0;
  const focus = applications === null
    ? { title: "Keep your search organized", detail: "Open your tracker to review the latest changes.", href: "/applications", cta: "Open tracker" }
    : interviewCount > 0
      ? { title: interviewCount + (interviewCount === 1 ? " interview in progress" : " interviews in progress"),
          detail: "Keep interview notes and the resume you used close to hand.", href: "/applications", cta: "Review interviews" }
      : tracked > 0
        ? { title: "Pick up your application tracker", detail: "Update a status, add a note, or review a recent submission.",
          href: "/applications", cta: "Review applications" }
        : resumeCount === 0
          ? { title: "Start with a resume", detail: "Save a resume version before comparing it with roles you discover.",
            href: "/resumes", cta: "Manage resumes" }
          : { title: "Find your next opportunity", detail: "Browse internship roles and save any worth researching.",
            href: "/jobs", cta: "Explore internships" };

  return (
    <section className="focus-section" aria-labelledby="focus-title">
      <div className="focus-heading">
        <div>
          <p className="focus-eyebrow">BACK TO YOUR SEARCH</p>
          <h2 id="focus-title">Continue where you left off</h2>
          <p>Applications, saved work, and your next move.</p>
        </div>
      </div>
      <div className="focus-layout">
        <div className="focus-primary">
          <span className="focus-primary-icon"><CalendarCheck2 size={24} aria-hidden="true" /></span>
          <div className="focus-primary-copy">
            <span className="focus-overline">YOUR NEXT MOVE</span>
            <h3>{focus.title}</h3>
            <p>{focus.detail}</p>
          </div>
          <Link href={focus.href} className="focus-primary-action">
            {focus.cta} <ArrowUpRight size={17} aria-hidden="true" />
          </Link>
        </div>
        <div className="focus-activity">
          <div className="focus-activity-heading">
            <div>
              <h3>Recent applications</h3>
              <p>{applications === null ? "Loading your tracker…" : tracked === 0 ?
                "Your tracker is ready." : tracked + (tracked === 1 ? " tracked application" : " tracked applications")}</p>
            </div>
            <ClipboardList size={20} aria-hidden="true" />
          </div>
          {applications?.length ? (
            <ul className="focus-applications">
              {(orderedApplications ?? []).slice(0, 3).map(item => (
                <li className="focus-application-row" key={item.id}>
                  <CompanyLogo company={item.company_name} />
                  <div className="focus-application-identity">
                    <strong title={item.job_title}>{item.job_title}</strong>
                    <span>{item.company_name}</span>
                  </div>
                  <span className="focus-stage" data-status={item.current_status}>
                    {statusLabels[item.current_status] ?? item.current_status}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="focus-empty" role={loadError ? "status" : undefined}>
              {loadError
                ? <><p>Some activity could not be loaded.</p><button className="focus-retry" onClick={() => setAttempt(n => n + 1)}>Try again</button></>
                : applications === null ? "Loading applications…" : "Once you track an application, it will appear here."}
            </div>
          )}
          <Link href="/applications" className="focus-secondary-link focus-activity-link">
            Manage applications <ArrowUpRight size={15} aria-hidden="true" />
          </Link>
        </div>
      </div>
      <nav className="focus-shortcuts" aria-label="Quick actions">
        <Link href="/jobs"><BriefcaseBusiness size={17} aria-hidden="true" /> Browse internships <ArrowUpRight size={15} aria-hidden="true" /></Link>
        <Link href="/resumes"><FileText size={17} aria-hidden="true" /> Open resumes <ArrowUpRight size={15} aria-hidden="true" /></Link>
        <Link href="/candidate"><UserRound size={17} aria-hidden="true" /> Review profile <ArrowUpRight size={15} aria-hidden="true" /></Link>
      </nav>
    </section>
  );
}
