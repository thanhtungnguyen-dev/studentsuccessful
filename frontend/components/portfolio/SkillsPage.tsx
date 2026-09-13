"use client";
import {useEffect,useRef,useState} from "react";
import {apiClient,ApiError,authErrorMessage} from "../../lib/api/client";
import {loadSkills,selection} from "../../lib/portfolio/form";
import {useAuth} from "../auth/AuthProvider";
import {PortfolioPage} from "./PortfolioPage";
import {SkillChoices} from "./SkillChoices";
export function SkillsPage(){return <PortfolioPage title="Skills"><SkillsContent/></PortfolioPage>;}
function SkillsContent(){
 const {refresh}=useAuth(),[data,setData]=useState<Awaited<ReturnType<typeof loadSkills>>|null>(null),[attempt,setAttempt]=useState(0),[error,setError]=useState(""),[success,setSuccess]=useState(""),[busy,setBusy]=useState(false),pending=useRef(false);
 useEffect(()=>{let active=true;setError("");loadSkills().then(value=>{if(active)setData(value);}).catch(error=>{if(active){setError(authErrorMessage(error));if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}});return()=>{active=false;};},[attempt,refresh]);
 async function save(){if(!data||pending.current)return;pending.current=true;setBusy(true);setError("");setSuccess("");try{const values=await apiClient.replaceSkills(data.values);setData({...data,values:selection(values)});setSuccess("Skills saved.");}catch(error){setError(authErrorMessage(error));if(error instanceof ApiError&&error.status===401)void refresh().catch(()=>{});}finally{pending.current=false;setBusy(false);}}
 return <><p className="muted">Skills you explicitly claim to know. Career preferences and project technologies do not add skills here.</p>
 {error&&<p role="alert" className="auth-error">{error}</p>}{!data ? error ? <button className="secondary" onClick={()=>setAttempt(x=>x+1)}>Retry Skills</button> : <p role="status">Loading skills…</p> : <form className="auth-card preferences-form" onSubmit={event=>{event.preventDefault();void save();}}><fieldset disabled={busy}>
 {!data.values.skill_ids.length&&!data.values.custom_values.length&&<p className="muted">No skills selected.</p>}
 <SkillChoices values={data.values} catalog={data.catalog} onChange={values=>{setData({...data,values:selection(values)});setSuccess("");}}/>
 <button className="primary" type="submit">{busy?"Saving…":"Save skills"}</button></fieldset></form>}
 {success&&<p role="status" className="profile-success">{success}</p>}</>;
}
