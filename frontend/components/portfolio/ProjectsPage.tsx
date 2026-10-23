"use client";
import { LoadingState } from "../ui/LoadingState";
import {useEffect,useRef,useState} from "react";
import {apiClient,ApiError,authErrorMessage,type Project,type ProjectCreate} from "../../lib/api/client";
import {loadProjects,projectPayload} from "../../lib/portfolio/form";
import {useAuth} from "../auth/AuthProvider";
import {PortfolioPage} from "./PortfolioPage";
import {safeApplicationUrl} from "../../lib/jobs/applicationUrl";
import {SkillChoices,SkillList} from "./SkillChoices";
const empty=():ProjectCreate=>({title:"",description:"",project_url:"",repository_url:"",technologies:{skill_ids:[],custom_values:[]}});
export function ProjectsPage(){return <PortfolioPage title="Projects"><ProjectsContent/></PortfolioPage>;}
function ProjectsContent(){
 const {refresh}=useAuth(),[data,setData]=useState<Awaited<ReturnType<typeof loadProjects>>|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState(""),[success,setSuccess]=useState(""),[busy,setBusy]=useState(false),pending=useRef(false);
 const [editing,setEditing]=useState<Project|"new"|null>(null),[form,setForm]=useState<ProjectCreate>(empty),[deleting,setDeleting]=useState<string|null>(null);
 const [search,setSearch]=useState("");
 useEffect(()=>{let active=true;setError("");loadProjects().then(value=>{if(active)setData(value);}).catch(error=>{if(active){setError(authErrorMessage(error));if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}});return()=>{active=false;};},[attempt,refresh]);
 const visibleProjects = data ? data.projects.filter(row => {
   const needle = search.toLowerCase().trim();
   if (!needle) return true;
   const technologies = (row.technologies?.skill_ids ?? []).map(id => data.catalog.find(skill => skill.id === id)?.name ?? "");
   return [row.title, row.description ?? "", ...technologies, ...(row.technologies?.custom_values ?? [])]
     .join(" ").toLowerCase().includes(needle);
 }) : [];
 function failure(error:unknown){setError(error instanceof ApiError?authErrorMessage(error):error instanceof Error?error.message:"Please try again.");if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}
 async function save(){if(!data||!editing||pending.current)return;setError("");setSuccess("");let values:ProjectCreate;try{values=projectPayload(form);}catch(error){failure(error);return;}pending.current=true;setBusy(true);try{const row=editing==="new"?await apiClient.createProject(values):await apiClient.updateProject(editing.id,values);setData({...data,projects:editing==="new"?[...data.projects,row]:data.projects.map(x=>x.id===row.id?row:x)});setEditing(null);setSuccess("Project saved.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 async function remove(){if(!data||!deleting||pending.current)return;pending.current=true;setBusy(true);setError("");setSuccess("");try{await apiClient.deleteProject(deleting);setData({...data,projects:data.projects.filter(x=>x.id!==deleting)});setDeleting(null);setSuccess("Project deleted.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 return <><p className="muted">Show what you built, the tools you used, and links to your work. Add skills separately to your profile.</p>
 {error&&<p role="alert" className="auth-error">{error}</p>}{success&&<p role="status" className="profile-success">{success}</p>}
 {!data ? error ? <button className="secondary" onClick={()=>setAttempt(x=>x+1)}>Retry Projects</button> : <LoadingState label="Loading projects…" /> : <>
 {!editing&&!deleting&&<button className="primary education-add" onClick={()=>{setForm(empty());setEditing("new");setError("");setSuccess("");}}>Add project</button>}
 {data.projects.length>=5&&!editing&&!deleting&&<div className="project-search">
   <label htmlFor="project-search-input">Find a project</label>
   <input id="project-search-input" type="search" value={search} placeholder="Search names, descriptions, or technologies" onChange={event=>setSearch(event.target.value)}/>
   <span role="status">{visibleProjects.length} of {data.projects.length} projects</span>
 </div>}
 {editing&&<form className="auth-card education-form" onSubmit={event=>{event.preventDefault();void save();}} noValidate><h2>{editing==="new"?"Add project":"Edit project"}</h2><fieldset disabled={busy}>
 <label>Title<input value={form.title} maxLength={150} required onChange={event=>setForm({...form,title:event.target.value})}/></label>
 <label htmlFor="project-description">Description</label><textarea id="project-description" value={form.description??""} maxLength={5000} onChange={event=>setForm({...form,description:event.target.value})}/>
 <label>Project URL<input type="url" value={form.project_url??""} maxLength={500} onChange={event=>setForm({...form,project_url:event.target.value})}/></label>
 <label>Repository URL<input type="url" value={form.repository_url??""} maxLength={500} onChange={event=>setForm({...form,repository_url:event.target.value})}/></label>
 <SkillChoices values={form.technologies??{}} catalog={data.catalog} onChange={technologies=>setForm({...form,technologies})}/>
 <div className="auth-actions"><button className="primary" type="submit">{busy?"Saving…":"Save project"}</button><button className="secondary" type="button" onClick={()=>setEditing(null)}>Cancel</button></div></fieldset></form>}
 <div className="education-list">{!data.projects.length&&<p className="muted">No projects saved. Add a project to highlight your work.</p>}{Boolean(search.trim())&&!visibleProjects.length&&<p className="muted">No projects match your search. Try another keyword.</p>}{visibleProjects.map(row=><article className="auth-card dashboard-card" key={row.id}><h2>{row.title}</h2><p className="project-description">{row.description||"No description provided."}</p><h3>Project technologies</h3><SkillList values={row.technologies??{}} catalog={data.catalog}/>
 <div className="project-external-links">
  {safeApplicationUrl(row.project_url ?? "") && <a className="secondary" href={safeApplicationUrl(row.project_url ?? "")!} target="_blank" rel="noopener noreferrer">Open project ↗</a>}
  {safeApplicationUrl(row.repository_url ?? "") && <a className="secondary" href={safeApplicationUrl(row.repository_url ?? "")!} target="_blank" rel="noopener noreferrer">View code ↗</a>}
  {!safeApplicationUrl(row.project_url ?? "") && !safeApplicationUrl(row.repository_url ?? "") && <p className="muted">Add a link so others can explore your work.</p>}
</div>
 {!editing&&!deleting&&<div className="auth-actions"><button className="secondary" aria-label={`Edit ${row.title}`} onClick={()=>{setEditing(row);setForm({title:row.title,description:row.description,project_url:row.project_url,repository_url:row.repository_url,technologies:row.technologies});setError("");setSuccess("");}}>Edit project</button><button className="secondary" aria-label={`Delete ${row.title}`} onClick={()=>setDeleting(row.id)}>Delete</button></div>}
 {deleting===row.id&&<div><p>Delete this project? Your Skills and Preferences will remain unchanged.</p><button className="secondary" disabled={busy} onClick={()=>void remove()}>{busy?"Deleting…":"Confirm delete"}</button><button className="secondary" disabled={busy} onClick={()=>setDeleting(null)}>Cancel deletion</button></div>}
 </article>)}</div></>}
 </>;
}
