"use client";
import {useState} from "react";
import type {SkillSelection,CatalogItem} from "../../lib/api/client";
import {selection,addCustomSkill} from "../../lib/portfolio/form";
export function SkillList({values,catalog}:{values:SkillSelection;catalog:CatalogItem[]}) {
 const state=selection(values);
 return !state.skill_ids.length && !state.custom_values.length ? <p className="muted">No skills or technologies saved.</p> : <ul>{state.skill_ids.map(id=><li key={id}>{catalog.find(item=>item.id===id)?.name ?? `Saved catalog selection (label unavailable): ${id}`}</li>)}{state.custom_values.map((value,i)=><li className="review-custom" key={`custom-${i}`}>{value} <span className="muted">(custom)</span></li>)}</ul>;
}
export function SkillChoices({values,catalog,onChange}:{values:SkillSelection;catalog:CatalogItem[];onChange:(value:SkillSelection)=>void}) {
 const state=selection(values),[other,setOther]=useState(""),[error,setError]=useState("");
 return <fieldset className="skill-choices"><legend>Skills / technologies</legend>
 {!catalog.length && <p className="muted">No catalog skills available. You can add an Other skill.</p>}
 <div className="preference-options">{catalog.map(item=><label key={item.id}><input type="checkbox" checked={state.skill_ids.includes(item.id)} onChange={()=>onChange({...state,skill_ids:state.skill_ids.includes(item.id)?state.skill_ids.filter(id=>id!==item.id):[...state.skill_ids,item.id]})}/>{item.name}</label>)}</div>
 {state.skill_ids.filter(id=>!catalog.some(item=>item.id===id)).map(id=><p key={id}>Saved catalog selection (label unavailable): {id} <button type="button" className="secondary" onClick={()=>onChange({...state,skill_ids:state.skill_ids.filter(x=>x!==id)})}>Remove unavailable skill</button></p>)}
 <label>Other skill<input value={other} maxLength={150} onChange={event=>setOther(event.target.value)}/></label>
 <button type="button" className="secondary" onClick={()=>{try{onChange(addCustomSkill(state,other,catalog));setOther("");setError("");}catch(error){setError((error as Error).message);}}}>Add Other skill</button>
 {error && <p role="alert" className="auth-error">{error}</p>}
 {state.custom_values.map((value,index)=><p className="preference-custom" key={index}><span>{value} (custom)</span><button type="button" className="secondary" aria-label={`Remove custom ${value}`} onClick={()=>onChange({...state,custom_values:state.custom_values.filter((_,i)=>i!==index)})}>Remove</button></p>)}
 </fieldset>;
}
