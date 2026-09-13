import {SkillList} from "./SkillChoices";
import {type loadSkills,type loadProjects} from "../../lib/portfolio/form";
export function SkillsSummary({data}:{data:Awaited<ReturnType<typeof loadSkills>>}) {
 return <><p className="muted">Skills you explicitly claim to know.</p>{!data.values.skill_ids.length&&!data.values.custom_values.length?<p className="muted">No factual skills saved.</p>:<SkillList values={data.values} catalog={data.catalog}/>}</>;
}
export function ProjectsSummary({data}:{data:Awaited<ReturnType<typeof loadProjects>>}) {
 return data.projects.length?<>{data.projects.map(row=><article key={row.id}><h3>{row.title}</h3><p className="project-description">{row.description?row.description.length>240?row.description.slice(0,240)+"…":row.description:"No description provided."}</p><h3>Project technologies</h3><SkillList values={row.technologies??{}} catalog={data.catalog}/></article>)}</>:<p className="muted">No projects saved.</p>;
}
