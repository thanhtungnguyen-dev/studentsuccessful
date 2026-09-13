"use client";

import {SkillsSummary,ProjectsSummary} from "../portfolio/PortfolioSummaries";
import {ArtifactSummary} from "../artifacts/ArtifactList";
import {ResumeSummary} from "../resumes/ResumesPage";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { ApiError, authErrorMessage } from "../../lib/api/client";
import { dashboardLoaders } from "../../lib/dashboard/data";
import { useAuth } from "../auth/AuthProvider";
import { ProfileSummary, EducationSummary, EmploymentSummary, AuthorizationSummary, PreferencesSummary } from "./Summaries";

type SectionState<T> = {status: "loading"} | {status: "error"; message: string} | {status: "ready"; data: T};
export function DashboardSectionContent<T>({state, title, retry, children}: {state: SectionState<T>; title: string; retry: () => void; children: (data: T) => ReactNode}) {
  if (state.status === "loading") return <p role="status">Loading {title.toLowerCase()}…</p>;
  if (state.status === "error") return <><p role="alert" className="auth-error">Could not load {title.toLowerCase()}. {state.message}</p><button className="secondary" onClick={retry}>Retry {title}</button></>;
  return children(state.data);
}
function DashboardCard<T>({title, href, load, children, wide = false}: {title: string; href: string; load: () => Promise<T>; children: (data: T, retry: () => void) => ReactNode; wide?: boolean}) {
  const {refresh}=useAuth();
  const [state,setState]=useState<SectionState<T>>({status:"loading"}),[attempt,setAttempt]=useState(0);
  useEffect(() => {
    let active=true;setState({status:"loading"});
    load().then(data => {if(active)setState({status:"ready",data});}).catch(error => {
      if(active){setState({status:"error",message:authErrorMessage(error)});if(error instanceof ApiError && error.status===401)void refresh().catch(() => {});}
    });
    return () => {active=false;};
  },[load,attempt,refresh]);
  const retry=() => setAttempt(value => value+1), id=`dashboard-${href.slice(1)}`;
  return <section className={`auth-card dashboard-card${wide ? " dashboard-wide" : ""}`} aria-labelledby={id}>
    <header><h2 id={id}>{title}</h2><Link className="secondary" href={href}>Edit {title}</Link></header>
    <DashboardSectionContent state={state} title={title} retry={retry}>{data => children(data,retry)}</DashboardSectionContent>
  </section>;
}
export function Dashboard() {
  return <div className="dashboard-grid">
    <section className="auth-card dashboard-card" aria-labelledby="dashboard-jobs"><header><h2 id="dashboard-jobs">Jobs</h2><Link className="secondary" href="/jobs">Browse Jobs</Link></header><p className="muted">Browse shared listings and their stated requirements.</p></section>
    <section className="auth-card dashboard-card" aria-labelledby="dashboard-candidate"><header><h2 id="dashboard-candidate">Candidate Profile</h2><Link className="secondary" href="/candidate">View Candidate Profile</Link></header><p className="muted">See saved facts, project use, and detected resume evidence with their sources.</p></section>
    <DashboardCard title="Application Profile" href="/profile" load={dashboardLoaders.profile}>{data => <ProfileSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Education" href="/education" load={dashboardLoaders.education}>{data => <EducationSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Employment" href="/employment" load={dashboardLoaders.employment}>{data => <EmploymentSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Work Authorization" href="/work-authorization" load={dashboardLoaders.authorization}>{data => <AuthorizationSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Skills" href="/skills" load={dashboardLoaders.skills}>{data => <SkillsSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Projects" href="/projects" load={dashboardLoaders.projects}>{data => <ProjectsSummary data={data}/>}</DashboardCard>
    <DashboardCard title="Career Artifacts" href="/artifacts" load={dashboardLoaders.artifacts}>{items => <ArtifactSummary items={items}/>}</DashboardCard>
    <DashboardCard title="Resumes" href="/resumes" load={dashboardLoaders.resumes}>{items => <ResumeSummary items={items}/>}</DashboardCard>
    <DashboardCard title="Career Preferences" href="/preferences" load={dashboardLoaders.preferences} wide>{(data,retry) => <>
      {data.labelsUnavailable && <><p role="alert" className="auth-error">Some catalog labels could not be loaded. Saved selections are still shown.</p><button className="secondary" onClick={retry}>Retry preference labels</button></>}
      <PreferencesSummary data={data}/>
    </>}</DashboardCard>
  </div>;
}
