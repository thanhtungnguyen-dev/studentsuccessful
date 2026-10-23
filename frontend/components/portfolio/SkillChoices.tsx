"use client";

import Image from "next/image";
import { ChevronDown, Code2, Search, X } from "lucide-react";
import { useState } from "react";
import type { SkillSelection, CatalogItem } from "../../lib/api/client";
import { selection, addCustomSkill } from "../../lib/portfolio/form";

function SkillIcon({ name }: { name: string }) {
  const key = name.toLowerCase().trim();
  if (key === "python") return <span className="candidate-tech-mark candidate-tech-mark--python"><Image src="/skill-icons/python.svg" width={25} height={25} alt="" unoptimized /></span>;
  const names: Record<string, [string, string]> = {
    javascript: ["JS", "javascript"], typescript: ["TS", "typescript"], react: ["⚛", "react"],
    "c++": ["C++", "cpp"], "c/c++": ["C++", "cpp"], postgresql: ["PG", "postgres"],
    sql: ["DB", "postgres"], git: ["Git", "git"], linux: ["Lx", "linux"],
    docker: ["D", "docker"], java: ["J", "java"], fastapi: ["F", "fastapi"],
    "next.js": ["N", "next"],
  };
  const value = names[key];
  return <span aria-hidden="true" className={`candidate-tech-mark candidate-tech-mark--${value?.[1] ?? "other"}`}>{value?.[0] ?? <Code2 size={16} />}</span>;
}

export function SkillList({ values, catalog }: { values: SkillSelection; catalog: CatalogItem[] }) {
  const state = selection(values);
  return !state.skill_ids.length && !state.custom_values.length ? <p className="muted">No skills or technologies saved.</p> :
    <ul className="skill-review-list">{state.skill_ids.map(id => {
      const name = catalog.find(item => item.id === id)?.name ?? `Unavailable catalog skill ${id}`;
      return <li key={id}><SkillIcon name={name} />{name}</li>;
    })}{state.custom_values.map((value, i) => <li key={`custom-${i}`}><SkillIcon name={value} />{value}</li>)}</ul>;
}

export function SkillChoices({ values, catalog, onChange }: { values: SkillSelection; catalog: CatalogItem[]; onChange: (value: SkillSelection) => void }) {
  const state = selection(values);
  const [other, setOther] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [showAll, setShowAll] = useState(false);
  const selected = new Set(state.skill_ids);
  const ordered = [...catalog].sort((a, b) => Number(selected.has(b.id)) - Number(selected.has(a.id)) || a.name.localeCompare(b.name));
  const filtered = ordered.filter(item => item.name.toLowerCase().includes(search.trim().toLowerCase()));
  const visible = search || showAll ? filtered : selected.size ? filtered.filter(item => selected.has(item.id)) : filtered.slice(0, 8);
  const count = state.skill_ids.length + state.custom_values.length;
  return <fieldset className="skill-choices skill-choices-refined">
    <legend>Skills & technologies</legend>
    <div className="skill-choices-toolbar">
      <span className="skill-selection-count">{count} selected</span>
      {catalog.length > 10 && <label className="skill-choices-search"><Search size={16} aria-hidden="true"/><span className="sr-only">Find skills</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search skills" autoComplete="off" /></label>}
    </div>
    {!catalog.length && <p className="muted">Catalog unavailable. You can still add a custom skill.</p>}
    {visible.length ? <div className="preference-options skill-choices-options">{visible.map(item => <label key={item.id} className={selected.has(item.id) ? "skill-option-is-selected" : ""}>
      <input type="checkbox" checked={selected.has(item.id)} onChange={() => onChange({ ...state, skill_ids: selected.has(item.id) ? state.skill_ids.filter(id => id !== item.id) : [...state.skill_ids, item.id] })} />
      <SkillIcon name={item.name} /><span>{item.name}</span>
    </label>)}</div> : <p className="candidate-empty">No skills found. Add a custom skill below.</p>}
    {!search && (showAll || filtered.length > visible.length) && <button type="button" className="candidate-show-more" aria-expanded={showAll} onClick={() => setShowAll(open => !open)}>{showAll ? "Show selected skills" : `Browse all ${catalog.length} skills`} <ChevronDown size={15} className={showAll ? "candidate-chevron-up" : ""}/></button>}
    {state.skill_ids.filter(id => !catalog.some(item => item.id === id)).map(id => <p key={id}>Saved skill without a catalog label: {id} <button type="button" className="secondary" onClick={() => onChange({ ...state, skill_ids: state.skill_ids.filter(x => x !== id) })}>Remove</button></p>)}
    <div className="skill-custom-entry"><label htmlFor="new-skill">Add a skill</label><div><input id="new-skill" value={other} maxLength={150} placeholder="e.g. Kubernetes" onChange={event => setOther(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); try { onChange(addCustomSkill(state, other, catalog)); setOther(""); setError(""); } catch (reason) { setError((reason as Error).message); } } }} /><button type="button" className="secondary" onClick={() => { try { onChange(addCustomSkill(state, other, catalog)); setOther(""); setError(""); } catch (reason) { setError((reason as Error).message); } }}>Add skill</button></div></div>
    {error && <p role="alert" className="auth-error">{error}</p>}
    {state.custom_values.length > 0 && <div className="skill-custom-chips" aria-label="Custom skills">{state.custom_values.map((value, index) => <span className="skill-custom-chip" key={`${value}-${index}`}><SkillIcon name={value} />{value}<button type="button" aria-label={`Remove ${value}`} onClick={() => onChange({ ...state, custom_values: state.custom_values.filter((_, i) => i !== index) })}><X size={15} /></button></span>)}</div>}
  </fieldset>;
}
