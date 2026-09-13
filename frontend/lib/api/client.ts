/**
 * Typed API client consuming generated OpenAPI schema.
 */

import type { paths } from "./schema";
import { readCsrfCookie } from "../auth/cookies";

export type RegisterRequest = paths["/api/v1/auth/register"]["post"]["requestBody"]["content"]["application/json"];
export type LoginRequest = paths["/api/v1/auth/login"]["post"]["requestBody"]["content"]["application/json"];
export type RegisterResponse = paths["/api/v1/auth/register"]["post"]["responses"][201]["content"]["application/json"];
export type LoginResponse = paths["/api/v1/auth/login"]["post"]["responses"][200]["content"]["application/json"];
export type CurrentUser = paths["/api/v1/auth/me"]["get"]["responses"][200]["content"]["application/json"];
export type LogoutResponse = paths["/api/v1/auth/logout"]["post"]["responses"][200]["content"]["application/json"];
export type Artifact = paths["/api/v1/artifacts"]["get"]["responses"][200]["content"]["application/json"][number];
export type ArtifactCreate = paths["/api/v1/artifacts"]["post"]["requestBody"]["content"]["application/json"];
export type ArtifactUpdate = paths["/api/v1/artifacts/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type Resume = paths["/api/v1/resumes"]["get"]["responses"][200]["content"]["application/json"][number];
export type ResumeCreate = paths["/api/v1/resumes"]["post"]["requestBody"]["content"]["application/json"];
export type ResumeUpdate = paths["/api/v1/resumes/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type ResumeVersion = paths["/api/v1/resumes/{id}/versions"]["get"]["responses"][200]["content"]["application/json"][number];
export type ResumePrimaryVersionUpdate = paths["/api/v1/resumes/{id}/primary-version"]["put"]["requestBody"]["content"]["application/json"];
export type ResumeEvidence = paths["/api/v1/resume-versions/{id}/evidence"]["get"]["responses"][200]["content"]["application/json"][number];
export type ResumeExtractedText = paths["/api/v1/resume-versions/{id}/extracted-text"]["get"]["responses"][200]["content"]["application/json"];
export type SkillSelection = paths["/api/v1/profile/skills"]["put"]["requestBody"]["content"]["application/json"];
export type Project = paths["/api/v1/profile/projects"]["get"]["responses"][200]["content"]["application/json"][number];
export type ProjectCreate = paths["/api/v1/profile/projects"]["post"]["requestBody"]["content"]["application/json"];
export type ProjectUpdate = paths["/api/v1/profile/projects/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type Profile = NonNullable<paths["/api/v1/profile"]["get"]["responses"][200]["content"]["application/json"]>;
export type ProfileUpdate = paths["/api/v1/profile"]["patch"]["requestBody"]["content"]["application/json"];

export type Education = paths["/api/v1/profile/education"]["get"]["responses"][200]["content"]["application/json"][number];
export type EducationCreate = paths["/api/v1/profile/education"]["post"]["requestBody"]["content"]["application/json"];
export type EducationUpdate = paths["/api/v1/profile/education/{id}"]["patch"]["requestBody"]["content"]["application/json"];

export type Preferences = paths["/api/v1/preferences"]["put"]["requestBody"]["content"]["application/json"];
export type CatalogItem = paths["/api/v1/catalog/roles"]["get"]["responses"][200]["content"]["application/json"][number];
export type CatalogLocation = paths["/api/v1/catalog/locations"]["get"]["responses"][200]["content"]["application/json"][number];
export type Employment = paths["/api/v1/profile/employment"]["get"]["responses"][200]["content"]["application/json"][number];
export type EmploymentCreate = paths["/api/v1/profile/employment"]["post"]["requestBody"]["content"]["application/json"];
export type EmploymentUpdate = paths["/api/v1/profile/employment/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type WorkAuthorization = paths["/api/v1/profile/work-authorizations"]["get"]["responses"][200]["content"]["application/json"][number];
export type WorkAuthorizationCreate = paths["/api/v1/profile/work-authorizations"]["post"]["requestBody"]["content"]["application/json"];
export type WorkAuthorizationUpdate = paths["/api/v1/profile/work-authorizations/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type CandidateProfile = paths["/api/v1/profile/candidate"]["get"]["responses"][200]["content"]["application/json"];
export type PublicJobSearch = paths["/api/v1/jobs"]["get"]["responses"][200]["content"]["application/json"];
export type PublicJob = PublicJobSearch["items"][number];
export type JobSearchParams = NonNullable<paths["/api/v1/jobs"]["get"]["parameters"]["query"]>;
export type PublicJobDetail = paths["/api/v1/jobs/{id}"]["get"]["responses"][200]["content"]["application/json"];
export type JobUserState = paths["/api/v1/jobs/{id}/state"]["patch"]["responses"][200]["content"]["application/json"];
export type JobUserStateUpdate = paths["/api/v1/jobs/{id}/state"]["patch"]["requestBody"]["content"]["application/json"];
export type SavedJobSearch = paths["/api/v1/saved-searches"]["get"]["responses"][200]["content"]["application/json"][number];
export type SavedJobSearchCreate = paths["/api/v1/saved-searches"]["post"]["requestBody"]["content"]["application/json"];
export type SavedJobSearchUpdate = paths["/api/v1/saved-searches/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type JobAlertInbox = paths["/api/v1/alerts"]["get"]["responses"][200]["content"]["application/json"];
export type JobAlert = JobAlertInbox["items"][number];
export type JobAlertReadState = paths["/api/v1/alerts/{id}"]["patch"]["responses"][200]["content"]["application/json"];
export type Application = paths["/api/v1/applications"]["get"]["responses"][200]["content"]["application/json"]["items"][number];
export type ApplicationCreate = paths["/api/v1/applications"]["post"]["requestBody"]["content"]["application/json"];
export type ApplicationUpdate = paths["/api/v1/applications/{id}"]["patch"]["requestBody"]["content"]["application/json"];
export type ApplicationFilterStatus = NonNullable<paths["/api/v1/applications"]["get"]["parameters"]["query"]>["status"];
export type FitAnalysis = paths["/api/v1/jobs/{id}/fit"]["get"]["responses"][200]["content"]["application/json"];
export type ResumeAlignment = paths["/api/v1/jobs/{id}/resume-alignment"]["get"]["responses"][200]["content"]["application/json"];
export type SkillGapAnalysis = paths["/api/v1/jobs/{id}/gaps"]["get"]["responses"][200]["content"]["application/json"];
export type ResumeImprovementPlan = paths["/api/v1/jobs/{id}/resume-plan"]["get"]["responses"][200]["content"]["application/json"];
export type ResumeTailoringDraft = paths["/api/v1/jobs/{id}/resume-draft"]["get"]["responses"][200]["content"]["application/json"];
export type ResumeTailoringReview = paths["/api/v1/jobs/{id}/resume-reviews"]["get"]["responses"][200]["content"]["application/json"];
export type ResumeTailoringReviewCreate = paths["/api/v1/jobs/{id}/resume-reviews"]["post"]["requestBody"]["content"]["application/json"];
export type ResumeTailoringReviewItemUpdate = paths["/api/v1/jobs/{id}/resume-reviews/{review_id}/items/{item_id}"]["patch"]["requestBody"]["content"]["application/json"];

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export function authErrorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

export type HealthLiveResponse =
  paths["/health/live"]["get"]["responses"][200]["content"]["application/json"];
export type HealthReadyResponse =
  paths["/health/ready"]["get"]["responses"][200]["content"]["application/json"];

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = "") {
    this.baseUrl = baseUrl;
  }

  private async authRequest<T>(path: string, options: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`/api/v1/auth/${path}`, {
        ...options, credentials: "same-origin", cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Please try again.");
    }
    if (!response.ok) {
      // Never display server detail, validation input, HTML, or exception text.
      let message = "Something went wrong. Please try again.";
      if (response.status === 401) message = path === "login"
        ? "Invalid email or password." : "Your session has ended. Please log in again.";
      if (response.status === 409 && path === "register") message = "An account with this email already exists. Please log in.";
      if (response.status === 422) message = "Please check your email and password and try again.";
      if (response.status === 403) message = path === "logout"
        ? "Could not log out securely. Please log in again, then retry logout."
        : "This request could not be accepted. Please reload and try again.";
      if (response.status >= 500) message = "StudentSuccessful is temporarily unavailable. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Please try again."); }
  }

  register(payload: RegisterRequest): Promise<RegisterResponse> {
    return this.authRequest("register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  }

  login(payload: LoginRequest): Promise<LoginResponse> {
    return this.authRequest("login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  }

  async getCurrentUser(): Promise<CurrentUser | null> {
    try { return await this.authRequest<CurrentUser>("me", { method: "GET" }); }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  }

  completeOnboarding(): Promise<CurrentUser> {
    const csrf = readCsrfCookie();
    if (!csrf) return Promise.reject(new ApiError(403, "Your security cookie is missing. Please log in again before completing onboarding."));
    return this.authRequest("onboarding/complete", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: "{}" });
  }

  logout(): Promise<LogoutResponse> {
    const csrf = readCsrfCookie();
    if (!csrf) return Promise.reject(new ApiError(403, "Could not log out securely. Please log in again, then retry logout."));
    return this.authRequest("logout", { method: "POST", headers: { "X-CSRF-Token": csrf } });
  }

  private async artifactRequest<T>(method:string, id?:string, payload?:ArtifactCreate|ArtifactUpdate):Promise<T> {
    const headers:Record<string,string>={};
    if(method!=="GET") {const csrf=readCsrfCookie();if(!csrf)throw new ApiError(403,"Your security cookie is missing. Please log in again before saving.");headers["X-CSRF-Token"]=csrf;}
    if(payload!==undefined)headers["Content-Type"]="application/json";
    let response:Response;
    try{response=await fetch(`/api/v1/artifacts${id===undefined?"":`/${encodeURIComponent(id)}`}`,{method,headers,...(payload===undefined?{}:{body:JSON.stringify(payload)}),credentials:"same-origin",cache:"no-store",signal:AbortSignal.timeout(10000)});}
    catch{throw new ApiError(0,"Unable to reach StudentSuccessful. Your edits are still here. Reload to check whether the change was saved before retrying.");}
    if(!response.ok)throw new ApiError(response.status,response.status===401?"Your session has ended. Please log in again.":response.status===403?"This change could not be authorized. Please log in again and retry.":response.status===404?"This Resume link is no longer available. Reload the list.":response.status===422?"Enter a title and an absolute http or https Resume URL without embedded credentials.":"Resume links could not be saved or loaded. Please try again.");
    if(response.status===204)return undefined as T;
    try{return await response.json() as T;}catch{throw new ApiError(response.status,"Unexpected response. Reload to check your saved Resume links.");}
  }
  listArtifacts():Promise<Artifact[]>{return this.artifactRequest("GET");}
  createArtifact(value:ArtifactCreate):Promise<Artifact>{return this.artifactRequest("POST",undefined,value);}
  updateArtifact(id:string,value:ArtifactUpdate):Promise<Artifact>{return this.artifactRequest("PATCH",id,value);}
  deleteArtifact(id:string):Promise<void>{return this.artifactRequest("DELETE",id);}

  private async resumeRequest<T>(path: string, method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE", payload?: ResumeCreate | ResumeUpdate | ResumePrimaryVersionUpdate | FormData): Promise<T> {
    const headers: Record<string, string> = {};
    if (method !== "GET") {
      const csrf = readCsrfCookie();
      if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before changing resumes.");
      headers["X-CSRF-Token"] = csrf;
    }
    if (payload !== undefined && !(payload instanceof FormData)) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/${path}`, {
        method, headers, ...(payload === undefined ? {} : { body: payload instanceof FormData ? payload : JSON.stringify(payload) }),
        credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Reload to check whether the change was saved before retrying.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This resume is no longer available. Reload the list."
        : response.status === 422 ? "Check the resume title and upload a valid PDF or DOCX no larger than 5 MB."
        : "Resumes could not be saved or loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload your resumes to check the saved information."); }
  }

  listResumes(): Promise<Resume[]> { return this.resumeRequest("resumes", "GET"); }
  createResume(payload: ResumeCreate): Promise<Resume> { return this.resumeRequest("resumes", "POST", payload); }
  updateResume(id: string, payload: ResumeUpdate): Promise<Resume> { return this.resumeRequest(`resumes/${encodeURIComponent(id)}`, "PATCH", payload); }
  deleteResume(id: string): Promise<void> { return this.resumeRequest(`resumes/${encodeURIComponent(id)}`, "DELETE"); }
  listResumeVersions(resumeId: string): Promise<ResumeVersion[]> { return this.resumeRequest(`resumes/${encodeURIComponent(resumeId)}/versions`, "GET"); }
  uploadResumeVersion(resumeId: string, file: File): Promise<ResumeVersion> {
    const form = new FormData(); form.append("file", file, file.name);
    return this.resumeRequest(`resumes/${encodeURIComponent(resumeId)}/versions`, "POST", form);
  }
  setResumePrimaryVersion(resumeId: string, payload: ResumePrimaryVersionUpdate): Promise<ResumeVersion> {
    return this.resumeRequest(`resumes/${encodeURIComponent(resumeId)}/primary-version`, "PUT", payload);
  }
  deleteResumeVersion(id: string): Promise<void> { return this.resumeRequest(`resume-versions/${encodeURIComponent(id)}`, "DELETE"); }
  resumeVersionFileUrl(id: string): string { return `/api/v1/resume-versions/${encodeURIComponent(id)}/file`; }
  parseResumeVersion(id: string): Promise<ResumeVersion> { return this.resumeRequest(`resume-versions/${encodeURIComponent(id)}/parse`, "POST"); }
  listResumeEvidence(id: string): Promise<ResumeEvidence[]> { return this.resumeRequest(`resume-versions/${encodeURIComponent(id)}/evidence`, "GET"); }
  getResumeExtractedText(id: string): Promise<ResumeExtractedText> { return this.resumeRequest(`resume-versions/${encodeURIComponent(id)}/extracted-text`, "GET"); }

  private async portfolioRequest<T>(path: string, method = "GET", payload?: SkillSelection | ProjectCreate | ProjectUpdate): Promise<T> {
    const headers: Record<string,string> = {};
    if (method !== "GET") {
      const csrf=readCsrfCookie();
      if (!csrf) throw new ApiError(403,"Your security cookie is missing. Please log in again before saving.");
      headers["X-CSRF-Token"]=csrf;
    }
    if(payload !== undefined) headers["Content-Type"]="application/json";
    let response: Response;
    try {response=await fetch(`/api/v1/profile/${path}`,{method,headers,...(payload === undefined ? {} : {body:JSON.stringify(payload)}),credentials:"same-origin",cache:"no-store",signal:AbortSignal.timeout(10000)});}
    catch {throw new ApiError(0,"Unable to reach StudentSuccessful. Your edits have not been discarded. Reload to check whether the change was saved before retrying.");}
    if(!response.ok) throw new ApiError(response.status,response.status===401 ? "Your session has ended. Please log in again." : response.status===403 ? "This change could not be authorized. Please log in again and retry." : response.status===404 ? "This project is no longer available. Reload the list." : response.status===422 ? "Check required text, URLs and duplicate skills. Use an existing catalog choice instead of a matching custom name or alias." : "Skills or projects could not be saved or loaded. Please try again.");
    if(response.status===204)return undefined as T;
    try{return await response.json() as T;}catch{throw new ApiError(response.status,"Unexpected response. Reload to check your saved information.");}
  }
  getSkills(): Promise<SkillSelection> {return this.portfolioRequest("skills");}
  replaceSkills(values: SkillSelection): Promise<SkillSelection> {return this.portfolioRequest("skills","PUT",values);}
  listProjects(): Promise<Project[]> {return this.portfolioRequest("projects");}
  createProject(values: ProjectCreate): Promise<Project> {return this.portfolioRequest("projects","POST",values);}
  updateProject(id: string, values: ProjectUpdate): Promise<Project> {return this.portfolioRequest(`projects/${encodeURIComponent(id)}`,"PATCH",values);}
  deleteProject(id: string): Promise<void> {return this.portfolioRequest(`projects/${encodeURIComponent(id)}`,"DELETE");}

  private async profileRequest<T>(options: RequestInit): Promise<T> {
    let response: Response;
    try {
      response = await fetch("/api/v1/profile", {
        ...options, credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Your edits have not been discarded.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "The update could not be authorized. Please log in again and retry."
        : response.status === 422 ? "Check the required names, field lengths, phone, country code and web links."
        : "Your profile could not be saved or loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Please reload your profile to check whether changes were saved."); }
  }

  getProfile(): Promise<Profile | null> {
    return this.profileRequest({ method: "GET" });
  }

  updateProfile(payload: ProfileUpdate): Promise<Profile> {
    const csrf = readCsrfCookie();
    if (!csrf) return Promise.reject(new ApiError(403, "Your security cookie is missing. Please log in again before saving."));
    return this.profileRequest({ method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(payload) });
  }

  async getCandidateProfile(): Promise<CandidateProfile> {
    let response: Response;
    try {
      response = await fetch("/api/v1/profile/candidate", {
        method: "GET", headers: {}, credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Please try again.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This profile could not be authorized. Please log in again and retry."
        : "Your Candidate Profile could not be loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as CandidateProfile; }
    catch { throw new ApiError(response.status, "Unexpected response. Please reload your Candidate Profile."); }
  }

  private async jobsRequest<T>(path: string): Promise<T> {
    let response: Response;
    try { response = await fetch(`/api/v1/jobs${path}`, { method: "GET", headers: {}, credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000) }); }
    catch { throw new ApiError(0, "Unable to reach StudentSuccessful. Please try again."); }
    if (!response.ok) throw new ApiError(response.status, response.status === 401 ? "Your session has ended. Please log in again." : "Jobs could not be loaded. Please try again.");
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Please reload Jobs."); }
  }
  private async jobsMutation<T>(method: "POST" | "PATCH", path: string, payload?: unknown): Promise<T> {
    const csrf = readCsrfCookie();
    if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before saving this review.");
    const headers: Record<string, string> = { "X-CSRF-Token": csrf };
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/jobs${path}`, {
        method,
        headers,
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Reload to check whether the review was saved before retrying.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This review change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This saved review is no longer available. Return to the tailoring draft and try again."
        : response.status === 409 ? "Finish every decision before finalizing. A finalized review cannot be changed."
        : response.status === 422 ? "Choose ACCEPT or REJECT, and enter non-empty user wording when editing."
        : "The resume review could not be saved. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload the review to check its saved state."); }
  }
  listJobs(params: JobSearchParams = {}): Promise<PublicJobSearch> {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === "") continue;
      if (Array.isArray(value)) {
        for (const item of value) if (item !== "") query.append(key, String(item));
      } else query.set(key, String(value));
    }
    return this.jobsRequest(query.size ? `?${query}` : "");
  }
  getJob(id: string): Promise<PublicJobDetail> { return this.jobsRequest(`/${encodeURIComponent(id)}`); }
  async updateJobState(id: string, payload: JobUserStateUpdate): Promise<JobUserState> {
    const csrf = readCsrfCookie();
    if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before changing this job.");
    let response: Response;
    try {
      response = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}/state`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify(payload),
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Reload to confirm this job state.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This job change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This job is no longer available."
        : response.status === 422 ? "This job change was not valid. Please try again."
        : "This job change could not be saved. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as JobUserState; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload to confirm this job state."); }
  }

  private async savedSearchRequest<T>(
    method: "GET" | "POST" | "PATCH" | "DELETE",
    path = "",
    payload?: unknown,
  ): Promise<T> {
    const isMutation = method !== "GET";
    const csrf = isMutation ? readCsrfCookie() : undefined;
    if (isMutation && !csrf) {
      throw new ApiError(403, "Your security cookie is missing. Please log in again before saving a search.");
    }
    const headers: Record<string, string> = {};
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/saved-searches${path}`, {
        method,
        headers,
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Please try again.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This saved search change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This saved search is no longer available."
        : response.status === 422 ? "Check the saved search name and filter criteria."
        : "This saved search could not be saved. Please try again.";
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload to confirm the saved search."); }
  }

  listSavedSearches(): Promise<SavedJobSearch[]> {
    return this.savedSearchRequest<SavedJobSearch[]>("GET");
  }
  createSavedSearch(payload: SavedJobSearchCreate): Promise<SavedJobSearch> {
    return this.savedSearchRequest<SavedJobSearch>("POST", "", payload);
  }
  updateSavedSearch(id: string, payload: SavedJobSearchUpdate): Promise<SavedJobSearch> {
    return this.savedSearchRequest<SavedJobSearch>("PATCH", `/${encodeURIComponent(id)}`, payload);
  }
  deleteSavedSearch(id: string): Promise<void> {
    return this.savedSearchRequest<void>("DELETE", `/${encodeURIComponent(id)}`);
  }
  private async alertRequest<T>(
    method: "GET" | "PATCH",
    path = "",
    payload?: { read: true },
  ): Promise<T> {
    const csrf = method === "PATCH" ? readCsrfCookie() : undefined;
    if (method === "PATCH" && !csrf) {
      throw new ApiError(403, "Your security cookie is missing. Please log in again before changing an alert.");
    }
    const headers: Record<string, string> = {};
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch("/api/v1/alerts" + path, {
        method,
        headers,
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Please try again.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This alert change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This alert is no longer available."
        : "Alerts could not be loaded or changed. Please try again.";
      throw new ApiError(response.status, message);
    }
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload alerts and try again."); }
  }

  listAlerts(): Promise<JobAlertInbox> {
    return this.alertRequest<JobAlertInbox>("GET");
  }
  markAlertRead(id: string): Promise<JobAlertReadState> {
    return this.alertRequest<JobAlertReadState>("PATCH", "/" + encodeURIComponent(id), { read: true });
  }

  getJobFit(id: string): Promise<FitAnalysis> { return this.jobsRequest(`/${encodeURIComponent(id)}/fit`); }
  getJobResumeAlignment(id: string, resumeVersionId: string): Promise<ResumeAlignment> {
    return this.jobsRequest(
      `/${encodeURIComponent(id)}/resume-alignment?resume_version_id=${encodeURIComponent(resumeVersionId)}`,
    );
  }
  getJobSkillGaps(id: string, resumeVersionId: string): Promise<SkillGapAnalysis> {
    return this.jobsRequest(
      `/${encodeURIComponent(id)}/gaps?resume_version_id=${encodeURIComponent(resumeVersionId)}`,
    );
  }
  getResumeImprovementPlan(id: string, resumeVersionId: string): Promise<ResumeImprovementPlan> {
    return this.jobsRequest(
      `/${encodeURIComponent(id)}/resume-plan?resume_version_id=${encodeURIComponent(resumeVersionId)}`,
    );
  }
  getResumeTailoringDraft(id: string, resumeVersionId: string): Promise<ResumeTailoringDraft> {
    return this.jobsRequest(
      `/${encodeURIComponent(id)}/resume-draft?resume_version_id=${encodeURIComponent(resumeVersionId)}`,
    );
  }
  getResumeTailoringReview(id: string, resumeVersionId: string): Promise<ResumeTailoringReview> {
    return this.jobsRequest(
      `/${encodeURIComponent(id)}/resume-reviews?resume_version_id=${encodeURIComponent(resumeVersionId)}`,
    );
  }
  createResumeTailoringReview(id: string, payload: ResumeTailoringReviewCreate): Promise<ResumeTailoringReview> {
    return this.jobsMutation("POST", `/${encodeURIComponent(id)}/resume-reviews`, payload);
  }
  updateResumeTailoringReviewItem(
    id: string,
    reviewId: string,
    itemId: string,
    payload: ResumeTailoringReviewItemUpdate,
  ): Promise<ResumeTailoringReview> {
    return this.jobsMutation(
      "PATCH",
      `/${encodeURIComponent(id)}/resume-reviews/${encodeURIComponent(reviewId)}/items/${encodeURIComponent(itemId)}`,
      payload,
    );
  }
  finalizeResumeTailoringReview(id: string, reviewId: string): Promise<ResumeTailoringReview> {
    return this.jobsMutation(
      "POST",
      `/${encodeURIComponent(id)}/resume-reviews/${encodeURIComponent(reviewId)}/finalize`,
    );
  }

  private async educationRequest<T>(method: "GET" | "POST" | "PATCH" | "DELETE", id?: string, payload?: EducationCreate | EducationUpdate): Promise<T> {
    const headers: Record<string, string> = {};
    if (method !== "GET") {
      const csrf = readCsrfCookie();
      if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before saving or deleting.");
      headers["X-CSRF-Token"] = csrf;
    }
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/profile/education${id === undefined ? "" : `/${encodeURIComponent(id)}`}`, {
        method, headers, ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch { throw new ApiError(0, "Unable to reach StudentSuccessful. Your edits have not been discarded. Reload to check whether the change was saved before retrying."); }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This education record is no longer available. Reload the list."
        : response.status === 422 ? "Check required fields, dates, and the GPA value, scale and inclusion setting."
        : "Education could not be saved or loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload education to check whether the change was saved."); }
  }

  listEducation(): Promise<Education[]> { return this.educationRequest("GET"); }
  createEducation(payload: EducationCreate): Promise<Education> { return this.educationRequest("POST", undefined, payload); }
  updateEducation(id: string, payload: EducationUpdate): Promise<Education> { return this.educationRequest("PATCH", id, payload); }
  deleteEducation(id: string): Promise<void> { return this.educationRequest("DELETE", id); }

  private async employmentRequest<T>(method: "GET" | "POST" | "PATCH" | "DELETE", id?: string, payload?: EmploymentCreate | EmploymentUpdate): Promise<T> {
    const headers: Record<string, string> = {};
    if (method !== "GET") {
      const csrf = readCsrfCookie();
      if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before saving or deleting.");
      headers["X-CSRF-Token"] = csrf;
    }
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/profile/employment${id === undefined ? "" : `/${encodeURIComponent(id)}`}`, {
        method, headers, ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch { throw new ApiError(0, "Unable to reach StudentSuccessful. Your edits have not been discarded. Reload to check whether the change was saved before retrying."); }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This employment record is no longer available. Reload the list."
        : response.status === 422 ? "Check required fields and dates. Non-current employment requires an end date; end date cannot precede start date."
        : "Employment could not be saved or loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload employment to check whether the change was saved."); }
  }

  listEmployment(): Promise<Employment[]> { return this.employmentRequest("GET"); }
  createEmployment(payload: EmploymentCreate): Promise<Employment> { return this.employmentRequest("POST", undefined, payload); }
  updateEmployment(id: string, payload: EmploymentUpdate): Promise<Employment> { return this.employmentRequest("PATCH", id, payload); }
  deleteEmployment(id: string): Promise<void> { return this.employmentRequest("DELETE", id); }

  private async workAuthorizationRequest<T>(method: "GET" | "POST" | "PATCH" | "DELETE", id?: string, payload?: WorkAuthorizationCreate | WorkAuthorizationUpdate): Promise<T> {
    const headers: Record<string, string> = {};
    if (method !== "GET") {
      const csrf = readCsrfCookie();
      if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before saving or deleting.");
      headers["X-CSRF-Token"] = csrf;
    }
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch(`/api/v1/profile/work-authorizations${id === undefined ? "" : `/${encodeURIComponent(id)}`}`, {
        method, headers, ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000),
      });
    } catch { throw new ApiError(0, "Unable to reach StudentSuccessful. Your edits have not been discarded. Reload to check whether the change was saved before retrying."); }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This work authorization record is no longer available. Reload the list."
        : response.status === 409 ? "You already have a record for this country. Edit that record or choose another country."
        : response.status === 422 ? "Check the two-letter country code, status, sponsorship answers and notes (255 characters maximum)."
        : "Work authorization could not be saved or loaded. Please try again.";
      throw new ApiError(response.status, message);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch { throw new ApiError(response.status, "Unexpected response. Reload work authorization to check whether the change was saved."); }
  }

  listWorkAuthorizations(): Promise<WorkAuthorization[]> { return this.workAuthorizationRequest("GET"); }
  createWorkAuthorization(payload: WorkAuthorizationCreate): Promise<WorkAuthorization> { return this.workAuthorizationRequest("POST", undefined, payload); }
  updateWorkAuthorization(id: string, payload: WorkAuthorizationUpdate): Promise<WorkAuthorization> { return this.workAuthorizationRequest("PATCH", id, payload); }
  deleteWorkAuthorization(id: string): Promise<void> { return this.workAuthorizationRequest("DELETE", id); }

  private async preferenceRequest<T>(path: string, payload?: Preferences): Promise<T> {
    const headers: Record<string, string> = {};
    if (payload !== undefined) {
      const csrf = readCsrfCookie();
      if (!csrf) throw new ApiError(403, "Your security cookie is missing. Please log in again before saving.");
      headers["X-CSRF-Token"] = csrf; headers["Content-Type"] = "application/json";
    }
    let response: Response;
    try { response = await fetch(`/api/v1/${path}`, { method: payload === undefined ? "GET" : "PUT", headers,
      ...(payload === undefined ? {} : { body: JSON.stringify(payload) }), credentials: "same-origin", cache: "no-store", signal: AbortSignal.timeout(10000) }); }
    catch { throw new ApiError(0, "Unable to reach StudentSuccessful. Your selections remain in the form. Reload to check whether saving succeeded before retrying."); }
    if (!response.ok) throw new ApiError(response.status, response.status === 401 ? "Your session has ended. Please log in again."
      : response.status === 403 ? "Saving could not be authorized. Please log in again."
      : response.status === 422 ? "Check your selections and custom values. A catalog choice may no longer exist or custom values may be duplicated."
      : "Preferences or catalogs could not be loaded or saved. Please try again.");
    try { return await response.json() as T; } catch { throw new ApiError(response.status, "Unexpected response. Reload to check saved preferences."); }
  }

  getPreferences(): Promise<Preferences> { return this.preferenceRequest("preferences"); }
  replacePreferences(payload: Preferences): Promise<Preferences> { return this.preferenceRequest("preferences", payload); }
  listRoles(params: NonNullable<paths["/api/v1/catalog/roles"]["get"]["parameters"]["query"]> = {}): Promise<CatalogItem[]> {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null).map(([key, value]) => [key, String(value)]));
    return this.preferenceRequest(`catalog/roles${query.size ? `?${query}` : ""}`);
  }
  listSkills(params: NonNullable<paths["/api/v1/catalog/skills"]["get"]["parameters"]["query"]> = {}): Promise<CatalogItem[]> {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null).map(([key, value]) => [key, String(value)]));
    return this.preferenceRequest(`catalog/skills${query.size ? `?${query}` : ""}`);
  }
  listCompanies(params: NonNullable<paths["/api/v1/catalog/companies"]["get"]["parameters"]["query"]> = {}): Promise<CatalogItem[]> {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null).map(([key, value]) => [key, String(value)]));
    return this.preferenceRequest(`catalog/companies${query.size ? `?${query}` : ""}`);
  }
  listLocations(params: NonNullable<paths["/api/v1/catalog/locations"]["get"]["parameters"]["query"]> = {}): Promise<CatalogLocation[]> {
    const query = new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== null).map(([key, value]) => [key, String(value)]));
    return this.preferenceRequest(`catalog/locations${query.size ? `?${query}` : ""}`);
  }
  listIndustries(): Promise<CatalogItem[]> { return this.preferenceRequest("catalog/industries"); }

  private async applicationRequest<T>(
    method: "GET" | "POST" | "PATCH",
    path = "",
    payload?: ApplicationCreate | ApplicationUpdate,
  ): Promise<T> {
    const csrf = method === "GET" ? undefined : readCsrfCookie();
    if (method !== "GET" && !csrf) {
      throw new ApiError(403, "Your security cookie is missing. Please log in again before tracking an application.");
    }
    const headers: Record<string, string> = {};
    if (csrf) headers["X-CSRF-Token"] = csrf;
    if (payload !== undefined) headers["Content-Type"] = "application/json";
    let response: Response;
    try {
      response = await fetch("/api/v1/applications" + path, {
        method,
        headers,
        ...(payload === undefined ? {} : { body: JSON.stringify(payload) }),
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(10000),
      });
    } catch {
      throw new ApiError(0, "Unable to reach StudentSuccessful. Reload to confirm your application tracking.");
    }
    if (!response.ok) {
      const message = response.status === 401 ? "Your session has ended. Please log in again."
        : response.status === 403 ? "This application change could not be authorized. Please log in again and retry."
        : response.status === 404 ? "This application is no longer available."
        : response.status === 409 ? "This application changed elsewhere. Refresh and try again."
        : response.status === 422 ? "Check the application date, status, and concise notes."
        : "Application tracking could not be saved. Please try again.";
      throw new ApiError(response.status, message);
    }
    try {
      return await response.json() as T;
    } catch {
      throw new ApiError(response.status, "Unexpected response. Reload Applications to confirm the change.");
    }
  }

  listApplications(status?: ApplicationFilterStatus): Promise<Application[]> {
    const query = status && status !== "ALL" ? "?status=" + encodeURIComponent(status) : "";
    return this.applicationRequest<{ items: Application[] }>("GET", query).then((result) => result.items);
  }
  createApplication(payload: ApplicationCreate): Promise<Application> {
    return this.applicationRequest<Application>("POST", "", payload);
  }
  getApplication(id: string): Promise<Application> {
    return this.applicationRequest<Application>("GET", "/" + encodeURIComponent(id));
  }
  updateApplication(id: string, payload: ApplicationUpdate): Promise<Application> {
    return this.applicationRequest<Application>("PATCH", "/" + encodeURIComponent(id), payload);
  }

  async getHealthLive(): Promise<HealthLiveResponse> {
    const res = await fetch(`${this.baseUrl}/health/live`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`Health live check failed: ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as HealthLiveResponse;
  }

  async getHealthReady(): Promise<HealthReadyResponse> {
    const res = await fetch(`${this.baseUrl}/health/ready`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
    });
    if (!res.ok && res.status !== 503) {
      throw new Error(`Health ready check request failed: ${res.status} ${res.statusText}`);
    }
    return (await res.json()) as HealthReadyResponse;
  }
}

export const apiClient = new ApiClient();
