"use client";
import {useEffect,useRef,useState} from "react";
import {apiClient,ApiError,authErrorMessage,type Project,type ProjectCreate} from "../../lib/api/client";
import {loadProjects,projectPayload} from "../../lib/portfolio/form";
import {useAuth} from "../auth/AuthProvider";
import {PortfolioPage} from "./PortfolioPage";
import {SkillChoices,SkillList} from "./SkillChoices";
const empty=():ProjectCreate=>({title:"",description:"",project_url:"",repository_url:"",technologies:{skill_ids:[],custom_values:[]}});
export function ProjectsPage(){return <PortfolioPage title="Projects"><ProjectsContent/></PortfolioPage>;}
function ProjectsContent(){
 const {refresh}=useAuth(),[data,setData]=useState<Awaited<ReturnType<typeof loadProjects>>|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState(""),[success,setSuccess]=useState(""),[busy,setBusy]=useState(false),pending=useRef(false);
 const [editing,setEditing]=useState<Project|"new"|null>(null),[form,setForm]=useState<ProjectCreate>(empty),[deleting,setDeleting]=useState<string|null>(null);
 useEffect(()=>{let active=true;setError("");loadProjects().then(value=>{if(active)setData(value);}).catch(error=>{if(active){setError(authErrorMessage(error));if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}});return()=>{active=false;};},[attempt,refresh]);
 function failure(error:unknown){setError(error instanceof ApiError?authErrorMessage(error):error instanceof Error?error.message:"Please try again.");if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}
 async function save(){if(!data||!editing||pending.current)return;setError("");setSuccess("");let values:ProjectCreate;try{values=projectPayload(form);}catch(error){failure(error);return;}pending.current=true;setBusy(true);try{const row=editing==="new"?await apiClient.createProject(values):await apiClient.updateProject(editing.id,values);setData({...data,projects:editing==="new"?[...data.projects,row]:data.projects.map(x=>x.id===row.id?row:x)});setEditing(null);setSuccess("Project saved.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 async function remove(){if(!data||!deleting||pending.current)return;pending.current=true;setBusy(true);setError("");setSuccess("");try{await apiClient.deleteProject(deleting);setData({...data,projects:data.projects.filter(x=>x.id!==deleting)});setDeleting(null);setSuccess("Project deleted.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 return <><p className="muted">Projects you created. Technologies apply to each project and do not automatically become user-level Skills.</p>
 {error&&<p role="alert" className="auth-error">{error}</p>}{success&&<p role="status" className="profile-success">{success}</p>}
 {!data ? error ? <button className="secondary" onClick={()=>setAttempt(x=>x+1)}>Retry Projects</button> : <p role="status">Loading projects…</p> : <>
 {!editing&&!deleting&&<button className="primary education-add" onClick={()=>{setForm(empty());setEditing("new");setError("");setSuccess("");}}>Add project</button>}
 {editing&&<form className="auth-card education-form" onSubmit={event=>{event.preventDefault();void save();}} noValidate><h2>{editing==="new"?"Add project":"Edit project"}</h2><fieldset disabled={busy}>
 <label>Title<input value={form.title} maxLength={150} required onChange={event=>setForm({...form,title:event.target.value})}/></label>
 <label htmlFor="project-description">Description</label><textarea id="project-description" value={form.description??""} maxLength={5000} onChange={event=>setForm({...form,description:event.target.value})}/>
 <label>Project URL<input type="url" value={form.project_url??""} maxLength={500} onChange={event=>setForm({...form,project_url:event.target.value})}/></label>
 <label>Repository URL<input type="url" value={form.repository_url??""} maxLength={500} onChange={event=>setForm({...form,repository_url:event.target.value})}/></label>
 <SkillChoices values={form.technologies??{}} catalog={data.catalog} onChange={technologies=>setForm({...form,technologies})}/>
 <div className="auth-actions"><button className="primary" type="submit">{busy?"Saving…":"Save project"}</button><button className="secondary" type="button" onClick={()=>setEditing(null)}>Cancel</button></div></fieldset></form>}
 <div className="education-list">{!data.projects.length&&<p className="muted">No projects saved.</p>}{data.projects.map(row=><article className="auth-card dashboard-card" key={row.id}><h2>{row.title}</h2><p className="project-description">{row.description||"No description provided."}</p><h3>Project technologies</h3><SkillList values={row.technologies??{}} catalog={data.catalog}/>
 <dl><div><dt>Project URL</dt><dd>{row.project_url||"Not provided"}</dd></div><div><dt>Repository URL</dt><dd>{row.repository_url||"Not provided"}</dd></div></dl>
 {!editing&&!deleting&&<div className="auth-actions"><button className="secondary" onClick={()=>{setEditing(row);setForm({title:row.title,description:row.description,project_url:row.project_url,repository_url:row.repository_url,technologies:row.technologies});setError("");setSuccess("");}}>Edit {row.title}</button><button className="secondary" onClick={()=>setDeleting(row.id)}>Delete {row.title}</button></div>}
 {deleting===row.id&&<div><p>Delete this project? Your Skills and Preferences will remain unchanged.</p><button className="secondary" disabled={busy} onClick={()=>void remove()}>{busy?"Deleting…":"Confirm delete"}</button><button className="secondary" disabled={busy} onClick={()=>setDeleting(null)}>Cancel deletion</button></div>}
 </article>)}</div></>}
 </>;
}
