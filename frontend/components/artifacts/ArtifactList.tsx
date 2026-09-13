import type {Artifact} from "../../lib/api/client";
export function ArtifactList({items}:{items:Artifact[]}) {
 return items.length ? <ul>{items.map(item=><li key={item.id}><a href={item.external_url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">Open {item.title} (external link)</a></li>)}</ul> : <p className="muted">No Resume links saved.</p>;
}
export function ArtifactSummary({items}:{items:Artifact[]}) {
 return <><p className="muted">Linked Resumes. Files remain with their external provider.</p>{items.length>0&&<p>{items.length} Resume {items.length===1?"link":"links"}</p>}<ArtifactList items={items}/></>;
}
