"use client";

import { WorkspaceMetrics } from "./WorkspaceMetrics";
import { WorkspaceFocus } from "./WorkspaceFocus";
import {SkillsSummary,ProjectsSummary} from "../portfolio/PortfolioSummaries";
import {ArtifactSummary} from "../artifacts/ArtifactList";
import {ResumeSummary} from "../resumes/ResumesPage";
import { SummaryDisclosure } from "../ui/summary-disclosure";
import { completePreferences } from "../../lib/preferences/form";
import { UserRound, GraduationCap, Building2, Globe2, SlidersHorizontal, ListChecks, FolderOpen, Files, Link2, type LucideIcon } from "lucide-react";
import { Reveal } from "../ui/Reveal";
import { Card } from "../ui/card";
import { Skeleton } from "../ui/skeleton";

import { useEffect, useState, type ReactNode } from "react";
import { ApiError, authErrorMessage } from "../../lib/api/client";
import { dashboardLoaders } from "../../lib/dashboard/data";
import { useAuth } from "../auth/AuthProvider";
import { ProfileSummary, EducationSummary, EmploymentSummary, AuthorizationSummary, PreferencesSummary } from "./Summaries";

type SectionState<T> = {status: "loading"} | {status: "error"; message: string} | {status: "ready"; data: T};
export function DashboardSectionContent<T>({state, title, retry, children}: {state: SectionState<T>; title: string; retry: () => void; children: (data: T) => ReactNode}) {
  if (state.status === "loading") return <div role="status"><span className="sr-only">Loading {title.toLowerCase()}…</span><Skeleton /><Skeleton className="skeleton-short" /></div>;
  if (state.status === "error") return <><p role="alert" className="auth-error">Could not load {title.toLowerCase()}. {state.message}</p><button className="secondary" onClick={retry}>Retry {title}</button></>;
  return children(state.data);
}
function DashboardCard<T>({title, href, load, children, summary, icon, profileControl = false}: {title: string; href: string; load: () => Promise<T>; children: (data: T, retry: () => void) => ReactNode; summary: (data: T) => string; icon: LucideIcon; profileControl?: boolean}) {
  const {refresh}=useAuth();
  const [state,setState]=useState<SectionState<T>>({status:"loading"}),[attempt,setAttempt]=useState(0);
  useEffect(() => {
    let active=true;setState({status:"loading"});
    load().then(data => {if(active)setState({status:"ready",data});}).catch(error => {
      if(active){setState({status:"error",message:authErrorMessage(error)});if(error instanceof ApiError && error.status===401)void refresh().catch(() => {});}
    });
    return () => {active=false;};
  },[load,attempt,refresh]);
  const retry=() => setAttempt(value => value+1);
  const status = state.status === "loading" ? "Loading…" : state.status === "error" ? "Unable to load — expand to retry" : summary(state.data);
  return <SummaryDisclosure title={title} href={href} status={status} icon={icon} profileControl={profileControl}>
    <DashboardSectionContent state={state} title={title} retry={retry}>{data => children(data,retry)}</DashboardSectionContent>
  </SummaryDisclosure>;
}
const count = (n: number, singular: string, plural = `${singular}s`) => `${n} ${n === 1 ? singular : plural}`;

export function Dashboard() {
  return <div className="dashboard-overview">
    <WorkspaceMetrics />
    <WorkspaceFocus />
    <Reveal as="section" className="overview-group" aria-labelledby="profile-overview-title">
      <div className="section-heading"><h2 id="profile-overview-title">Profile overview</h2></div>
      <Card className="summary-list">
        <DashboardCard profileControl title="Personal Information" href="/profile" icon={UserRound} summary={data => data ? "Profile saved" : "Not provided"} load={dashboardLoaders.profile}>{data => <ProfileSummary data={data}/>}</DashboardCard>
        <DashboardCard profileControl title="Education" href="/education" icon={GraduationCap} summary={data => count(data.length,"school")} load={dashboardLoaders.education}>{data => <EducationSummary data={data}/>}</DashboardCard>
        <DashboardCard profileControl title="Employment" href="/employment" icon={Building2} summary={data => count(data.length,"record")} load={dashboardLoaders.employment}>{data => <EmploymentSummary data={data}/>}</DashboardCard>
        <DashboardCard profileControl title="Work Authorization" href="/work-authorization" icon={Globe2} summary={data => data.length ? `${count(data.length,"country","countries")} recorded` : "Not provided"} load={dashboardLoaders.authorization}>{data => <AuthorizationSummary data={data}/>}</DashboardCard>
        <DashboardCard profileControl title="Career Preferences" href="/preferences" icon={SlidersHorizontal} summary={data => {
          const total = Object.values(completePreferences(data.preferences)).reduce((sum, items) => sum + items.length, 0);
          return `${total ? count(total,"selection") : "Not configured"}${data.labelsUnavailable ? " · Some labels unavailable" : ""}`;
        }} load={dashboardLoaders.preferences}>{(data,retry) => <>
          {data.labelsUnavailable && <><p role="alert" className="auth-error">Some catalog labels could not be loaded. Saved selections are still shown.</p><button className="secondary" onClick={retry}>Retry preference labels</button></>}
          <PreferencesSummary data={data} compact/>
        </>}</DashboardCard>
        <DashboardCard profileControl title="Skills" href="/skills" icon={ListChecks} summary={data => count(data.values.skill_ids.length + data.values.custom_values.length,"skill")} load={dashboardLoaders.skills}>{data => <SkillsSummary data={data}/>}</DashboardCard>
        <DashboardCard profileControl title="Projects" href="/projects" icon={FolderOpen} summary={data => count(data.projects.length,"project")} load={dashboardLoaders.projects}>{data => <ProjectsSummary data={data}/>}</DashboardCard>
      </Card>
    </Reveal>
    <Reveal as="section" className="overview-group" aria-labelledby="resume-overview-title">
      <div className="section-heading"><h2 id="resume-overview-title">Resumes &amp; links</h2><p>Uploaded files and external links stay distinct.</p></div>
      <Card className="summary-list">
        <DashboardCard profileControl title="Managed Resumes" href="/resumes" icon={Files} summary={items => `${count(items.length,"resume")} · uploaded files`} load={dashboardLoaders.resumes}>{items => <ResumeSummary items={items}/>}</DashboardCard>
        <DashboardCard profileControl title="Career Artifacts" href="/artifacts" icon={Link2} summary={items => `${count(items.length,"artifact")} · external links`} load={dashboardLoaders.artifacts}>{items => <ArtifactSummary items={items}/>}</DashboardCard>
      </Card>
    </Reveal>
  </div>;
}
