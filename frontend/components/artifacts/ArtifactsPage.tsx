"use client";
import {useEffect,useRef,useState} from "react";
import {apiClient,ApiError,authErrorMessage,type Artifact,type ArtifactCreate} from "../../lib/api/client";
import {artifactPayload} from "../../lib/artifacts/form";
import {PortfolioPage} from "../portfolio/PortfolioPage";
import {useAuth} from "../auth/AuthProvider";
import {ArtifactList} from "./ArtifactList";
const empty=():ArtifactCreate=>({artifact_type:"RESUME",title:"",external_url:""});
export function ArtifactsPage(){return <PortfolioPage title="Career Artifacts"><ArtifactContent/></PortfolioPage>;}
function ArtifactContent(){
 const {refresh}=useAuth(),[items,setItems]=useState<Artifact[]|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState(""),[success,setSuccess]=useState(""),[busy,setBusy]=useState(false),pending=useRef(false);
 const [editing,setEditing]=useState<Artifact|"new"|null>(null),[form,setForm]=useState<ArtifactCreate>(empty),[deleting,setDeleting]=useState<string|null>(null);
 function failure(error:unknown){setError(error instanceof ApiError?authErrorMessage(error):error instanceof Error?error.message:"Please try again.");if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}
 useEffect(()=>{let active=true;setError("");apiClient.listArtifacts().then(data=>{if(active)setItems(data);}).catch(error=>{if(active){setError(authErrorMessage(error));if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}});return()=>{active=false;};},[attempt,refresh]);
 async function save(){if(!items||!editing||pending.current)return;setError("");setSuccess("");let value:ArtifactCreate;try{value=artifactPayload(form);}catch(error){failure(error);return;}pending.current=true;setBusy(true);try{const row=editing==="new"?await apiClient.createArtifact(value):await apiClient.updateArtifact(editing.id,value);setItems(editing==="new"?[...items,row]:items.map(item=>item.id===row.id?row:item));setEditing(null);setSuccess("Resume link saved.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 async function remove(){if(!items||!deleting||pending.current)return;pending.current=true;setBusy(true);setError("");setSuccess("");try{await apiClient.deleteArtifact(deleting);setItems(items.filter(item=>item.id!==deleting));setDeleting(null);setSuccess("Resume link removed.");}catch(error){failure(error);}finally{pending.current=false;setBusy(false);}}
 return <><p className="muted">Save links to your Resumes. StudentSuccessful stores the title and link, not the file. Your provider controls file access and availability. Resume links do not update your profile, Skills or Projects.</p>
 {error&&<p role="alert" className="auth-error">{error}</p>}{success&&<p role="status" className="profile-success">{success}</p>}
 {items===null ? error ? <button className="secondary" onClick={()=>setAttempt(x=>x+1)}>Retry Resume links</button> : <p role="status">Loading Resume links…</p> : <>
 {!editing&&!deleting&&<button className="primary education-add" onClick={()=>{setEditing("new");setForm(empty());setError("");setSuccess("");}}>Add Resume</button>}
 {editing&&<form className="auth-card education-form" onSubmit={event=>{event.preventDefault();void save();}} noValidate><h2>{editing==="new"?"Add Resume link":"Edit Resume link"}</h2><fieldset disabled={busy}>
 <label htmlFor="artifact-title">Resume title</label><input id="artifact-title" value={form.title} maxLength={150} required onChange={event=>setForm({...form,title:event.target.value})}/>
 <label htmlFor="artifact-url">External Resume URL</label><input id="artifact-url" type="url" value={form.external_url} maxLength={500} required onChange={event=>setForm({...form,external_url:event.target.value})}/>
 <div className="auth-actions"><button className="primary" type="submit">{busy?"Saving…":"Save Resume link"}</button><button className="secondary" type="button" onClick={()=>setEditing(null)}>Cancel</button></div></fieldset></form>}
 <div className="education-list">{!items.length&&<p className="muted">No Resume links saved.</p>}{items.map(item=><article className="auth-card dashboard-card artifact-card" key={item.id}><h2>{item.title}</h2><p className="muted">Resume · external link</p><ArtifactList items={[item]}/><p className="artifact-reference">{item.external_url}</p>
 {!editing&&!deleting&&<div className="auth-actions"><button className="secondary" onClick={()=>{setEditing(item);setForm({artifact_type:"RESUME",title:item.title,external_url:item.external_url});setError("");setSuccess("");}}>Edit {item.title}</button><button className="secondary" onClick={()=>setDeleting(item.id)}>Remove {item.title}</button></div>}
 {deleting===item.id&&<><p>Remove this saved link? The external file and your profile data will remain unchanged.</p><div className="auth-actions"><button className="secondary" disabled={busy} onClick={()=>void remove()}>{busy?"Removing…":"Confirm remove"}</button><button className="secondary" disabled={busy} onClick={()=>setDeleting(null)}>Cancel removal</button></div></>}
 </article>)}</div></>}
 </>;
}
