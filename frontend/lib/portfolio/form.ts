import {apiClient, type SkillSelection, type CatalogItem, type ProjectCreate} from "../api/client";
export function selection(value: SkillSelection = {}): Required<SkillSelection> {return {skill_ids:value.skill_ids ?? [],custom_values:value.custom_values ?? []};}
export const normalizeSkill=(value:string)=>value.trim().replace(/\s+/g," ").toLowerCase();
export function addCustomSkill(current: SkillSelection, value:string, catalog:CatalogItem[]): Required<SkillSelection> {
  const result=selection(current),key=normalizeSkill(value);
  if(!key || value.length>150)throw new Error("Enter an Other skill of 1–150 characters.");
  if(result.custom_values.some(item=>normalizeSkill(item)===key))throw new Error("This Other skill is already selected.");
  if(catalog.some(item=>normalizeSkill(item.name)===key))throw new Error("Choose this skill from the catalog instead.");
  return {...result,custom_values:[...result.custom_values,value]};
}
export function projectPayload(value:ProjectCreate): ProjectCreate {
  if(!value.title.trim() || value.title.length>150)throw new Error("Enter a project title of 1–150 characters.");
  if((value.description ?? "").length>5000)throw new Error("Description must be at most 5000 characters.");
  for(const text of [value.project_url,value.repository_url])if(text?.trim()){
    try {const url=new URL(text.trim());if(!["http:","https:"].includes(url.protocol)||url.username||url.password||/[\s\\]/.test(text.trim()))throw new Error();}
    catch {throw new Error("Use absolute http or https links without embedded credentials.");}
  }
  return {...value,project_url:value.project_url?.trim()||null,repository_url:value.repository_url?.trim()||null,technologies:selection(value.technologies)};
}
export async function loadSkills(){const [values,catalog]=await Promise.all([apiClient.getSkills(),apiClient.listSkills()]);return {values:selection(values),catalog};}
export async function loadProjects(){const [projects,catalog]=await Promise.all([apiClient.listProjects(),apiClient.listSkills()]);return {projects,catalog};}
