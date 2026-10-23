"use client";

import Link from "next/link";
import { BriefcaseBusiness, ClipboardCheck, Files, ArrowUpRight } from "lucide-react";
import { useEffect, useState } from "react";
import { apiClient } from "../../lib/api/client";

type Counts = { jobs: number | null; applications: number | null; resumes: number | null };

/** Real API totals on production; the same API client uses the local store in demo mode. */
export function WorkspaceMetrics() {
  const [counts, setCounts] = useState<Counts>({ jobs: null, applications: null, resumes: null });
  useEffect(() => {
    let active = true;
    Promise.allSettled([
      apiClient.listJobs({ page: 1, page_size: 1 }),
      apiClient.listApplications(),
      apiClient.listResumes(),
    ]).then(([jobs, applications, resumes]) => {
      if (!active) return;
      setCounts({
        jobs: jobs.status === "fulfilled" ? jobs.value.total : null,
        applications: applications.status === "fulfilled" ? applications.value.length : null,
        resumes: resumes.status === "fulfilled" ? resumes.value.length : null,
      });
    });
    return () => { active = false; };
  }, []);
  const cards = [
    { label: "Roles in catalog", value: counts.jobs, href: "/jobs", help: "Browse jobs", icon: BriefcaseBusiness },
    { label: "Applications", value: counts.applications, href: "/applications", help: "Open tracker", icon: ClipboardCheck },
    { label: "Resumes", value: counts.resumes, href: "/resumes", help: "Review resumes", icon: Files },
  ];
  return (
    <section className="workspace-metrics" aria-label="Workspace overview">
      {cards.map(({ label, value, href, help, icon: Icon }) => (
        <Link href={href} className="ui-card workspace-metric" key={href}>
          <span className="workspace-metric-head"><span>{label}</span><Icon size={19} aria-hidden="true" /></span>
          {value === null ? <span className="workspace-metric-number" aria-label={`${label} unavailable`}>—</span>
            : <strong className="workspace-metric-number">{value.toLocaleString()}</strong>}
          <span className="workspace-metric-hint">{help} <ArrowUpRight size={12} aria-hidden="true" className="inline" /></span>
        </Link>
      ))}
    </section>
  );
}
