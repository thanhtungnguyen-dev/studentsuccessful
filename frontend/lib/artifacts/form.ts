import type {ArtifactCreate} from "../api/client";
export function artifactPayload(value:ArtifactCreate):ArtifactCreate {
 if(!value.title.trim()||value.title.length>150)throw new Error("Enter a Resume title of 1–150 characters.");
 const reference=value.external_url.trim();
 try{const url=new URL(reference);if(!["http:","https:"].includes(url.protocol)||!url.hostname||url.username||url.password||/[\s\\]/.test(reference)||reference.length>500)throw new Error();}
 catch{throw new Error("Use an absolute http or https Resume URL without embedded credentials.");}
 return {artifact_type:"RESUME",title:value.title,external_url:reference};
}
