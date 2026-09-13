import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { afterEach, expect, it, vi } from "vitest";
import { apiClient, ApiError, type CurrentUser, type Education, type Employment, type WorkAuthorization } from "../api/client";
import { dashboardLoaders, type DashboardPreferences } from "./data";
import { ProfileSummary, EducationSummary, EmploymentSummary, AuthorizationSummary, PreferencesSummary } from "../../components/dashboard/Summaries";
import { Dashboard, DashboardSectionContent } from "../../components/dashboard/Dashboard";
import { AuthStatus } from "../../components/auth/AuthStatus";
import { postAuthDestination } from "../onboarding/routing";

const state=vi.hoisted(() => ({user:undefined as CurrentUser | null | undefined,error:""}));
vi.mock("../../components/auth/AuthProvider", () => ({useAuth:() => ({...state,refresh:vi.fn()})}));
afterEach(() => {vi.restoreAllMocks();state.user=undefined;state.error="";});
const user:CurrentUser={id:"owner",email:"owner@example.com",is_active:true,created_at:"2026-01-01T00:00:00Z",onboarding_completed_at:"2026-09-08T00:00:00Z"};
const metadata={id:"row",created_at:"2026-01-01T00:00:00Z",updated_at:"2026-01-01T00:00:00Z"};
const education:Education={...metadata,institution_name:"Example University",degree_level:"BS",major:"Computing",study_year:"YEAR_2",start_date:"2025-01-01",expected_grad_month:5,expected_grad_year:2028,is_primary:true,gpa_include_on_apps:false};
const employment:Employment={...metadata,employer_name:"Example Employer",job_title:"Developer",start_date:"2026-01-01",end_date:"2027-05-01",currently_employed:true};
const authorization:WorkAuthorization={...metadata,country_code:"CA",authorization_status:"OTHER",requires_current_sponsorship:false,requires_future_sponsorship:true,last_confirmed_at:"2026-09-08T00:00:00Z"};
const preferences:DashboardPreferences={preferences:{},labelsUnavailable:false,catalogs:{role_ids:[],industry_ids:[],location_ids:[],company_ids:[],skill_ids:[]}};

it("completed Home renders a dashboard with account context and five sections", () => {
 state.user=user;const html=render(h(AuthStatus));expect(html).toContain('>Home</h1>');expect(html).toContain(user.email);expect(html).toContain('dashboard-grid');expect(html).not.toContain('Continue onboarding');
 for(const title of ['Application Profile','Education','Employment','Work Authorization','Career Preferences'])expect(html).toContain('Edit '+title);expect(html).toContain('href="/candidate"');expect(html).toContain('View Candidate Profile');expect(html).toContain('href="/jobs"');expect(html).toContain('Browse Jobs');
});
it("renders saved profile facts with existing field labels", () => {
 const html=render(h(ProfileSummary,{data:{legal_first_name:"Ada",legal_last_name:"Lovelace",preferred_name:"A",address_city:"Calgary"}}));
 for(const text of ['Ada','Lovelace','Calgary','Legal first name','Preferred name','Not provided'])expect(html).toContain(text);
});
it("renders multiple saved education entries and primary designation", () => {
 const html=render(h(EducationSummary,{data:[education,{...education,id:"second",institution_name:"Second College",is_primary:false}]}));
 for(const text of ['Example University','Second College','Computing','2028-05','Primary education','<dd>Yes</dd>','<dd>No</dd>'])expect(html).toContain(text);
});
it("preserves current employment and its explicitly saved end date without inference", () => {
 const html=render(h(EmploymentSummary,{data:[employment]}));
 for(const text of ['Example Employer','Developer','2026-01-01','2027-05-01','Currently employed','<dd>Yes</dd>'])expect(html).toContain(text);
 expect(html).not.toContain('Present');
});
it("renders explicit work authorization and both sponsorship answers", () => {
 const html=render(h(AuthorizationSummary,{data:[authorization]}));
 for(const text of ['CA','Other','Current sponsorship required','Future sponsorship required','<dd>No</dd>','<dd>Yes</dd>'])expect(html).toContain(text);
});
it("renders structured preferences, exact custom text and unavailable label fallback", () => {
 const data:DashboardPreferences={...preferences,preferences:{role_ids:['role'],skill_ids:['missing'],work_modes:['ON_SITE'],employment_types:['CO_OP'],custom_values:[{preference_type:'SKILL',value:'  <b>Rust interest</b>  '}]},catalogs:{...preferences.catalogs,role_ids:[{id:'role',name:'Developer',is_active:false}]}};
 const html=render(h(PreferencesSummary,{data}));
 for(const text of ['Developer','ON SITE','CO OP','Technology interests','not skill claims','label unavailable','missing','  &lt;b&gt;Rust interest&lt;/b&gt;  ','(custom)'])expect(html).toContain(text);
 for(const title of ['Skills','Expertise','Qualifications','Experience'])expect(html).not.toContain('>'+title+'</h3>');
});
it("shows explicit empty optional sections without implying incomplete onboarding", () => {
 const html=[render(h(ProfileSummary,{data:null})),render(h(EducationSummary,{data:[]})),render(h(EmploymentSummary,{data:[]})),render(h(AuthorizationSummary,{data:[]})),render(h(PreferencesSummary,{data:preferences}))].join('');
 for(const text of ['No profile saved','No education records','No employment records','No work authorization records','No selections saved','Not provided'])expect(html).toContain(text);
 expect(html).not.toContain('incomplete');expect(html).not.toContain('100%');
});
it("renders loading without a misleading empty state", () => {
 const html=render(h(DashboardSectionContent<string>,{state:{status:'loading'},title:'Education',retry:vi.fn(),children:value => h('p',null,value)}));
 expect(html).toContain('role="status"');expect(html).toContain('Loading education');expect(html).not.toContain('No education');
});
it("renders understandable failure and a keyboard-accessible section retry", () => {
 const html=render(h(DashboardSectionContent<string>,{state:{status:'error',message:'Please try again.'},title:'Education',retry:vi.fn(),children:value => h('p',null,value)}));
 expect(html).toContain('role="alert"');expect(html).toContain('Could not load education');expect(html).toContain('<button');expect(html).toContain('Retry Education');expect(html).not.toContain('No education');
});
it.each([['Application Profile','/profile'],['Education','/education'],['Employment','/employment'],['Work Authorization','/work-authorization'],['Career Preferences','/preferences']])("routes %s editing to %s", (title,route) => {
 const html=render(h(Dashboard));expect(html).toContain(`href="${route}">Edit ${title}</a>`);
});
it("loads persisted values again on remount/refresh with no dashboard write operation", async () => {
 const read=vi.spyOn(apiClient,'getProfile').mockResolvedValueOnce({legal_first_name:'Ada',legal_last_name:'Lovelace'}).mockResolvedValueOnce({legal_first_name:'Updated',legal_last_name:'Lovelace'});
 const write=vi.spyOn(apiClient,'updateProfile');
 expect((await dashboardLoaders.profile())?.legal_first_name).toBe('Ada');expect((await dashboardLoaders.profile())?.legal_first_name).toBe('Updated');expect(read).toHaveBeenCalledTimes(2);expect(write).not.toHaveBeenCalled();
});
it("keeps independently successful data available when another loader fails", async () => {
 vi.spyOn(apiClient,'listEducation').mockResolvedValue([education]);vi.spyOn(apiClient,'listEmployment').mockRejectedValue(new ApiError(503,'Unavailable'));
 const [good,bad]=await Promise.allSettled([dashboardLoaders.education(),dashboardLoaders.employment()]);expect(good).toEqual({status:'fulfilled',value:[education]});expect(bad.status).toBe('rejected');
});
function catalogs(){
 vi.spyOn(apiClient,'getPreferences').mockResolvedValue({role_ids:['inactive'],custom_values:[{preference_type:'ROLE',value:'My choice'}]});
 vi.spyOn(apiClient,'listRoles').mockImplementation(async options => options?.active===false ? [{id:'inactive',name:'Saved inactive role',is_active:false}] : []);
 vi.spyOn(apiClient,'listIndustries').mockResolvedValue([]);vi.spyOn(apiClient,'listLocations').mockResolvedValue([{id:'place',country_code:'CA',city:'Calgary',state_province:'Alberta'}]);vi.spyOn(apiClient,'listCompanies').mockResolvedValue([]);vi.spyOn(apiClient,'listSkills').mockResolvedValue([]);
}
it("resolves saved inactive catalog choices and location labels", async () => {
 catalogs();const data=await dashboardLoaders.preferences();expect(data.catalogs.role_ids[0].name).toBe('Saved inactive role');expect(data.catalogs.location_ids[0].name).toBe('Calgary, Alberta, CA');expect(data.labelsUnavailable).toBe(false);
});
it("preserves preferences and surviving labels when a catalog fails", async () => {
 catalogs();vi.mocked(apiClient.listSkills).mockRejectedValue(new ApiError(503,'Unavailable'));
 const data=await dashboardLoaders.preferences();expect(data.labelsUnavailable).toBe(true);expect(data.preferences.custom_values?.[0].value).toBe('My choice');expect(data.catalogs.role_ids[0].name).toBe('Saved inactive role');
});
it.each([401,503])("does not turn failed preferences (%s) into empty choices", async status => {
 catalogs();vi.mocked(apiClient.getPreferences).mockRejectedValue(new ApiError(status,'Unavailable'));await expect(dashboardLoaders.preferences()).rejects.toMatchObject({status});
});
it("propagates a catalog authentication failure to session handling", async () => {
 catalogs();vi.mocked(apiClient.listSkills).mockRejectedValue(new ApiError(401,'Expired'));await expect(dashboardLoaders.preferences()).rejects.toMatchObject({status:401});
});
it("preserves incomplete login/review routing and does not show the dashboard", () => {
 state.user={...user,onboarding_completed_at:null};expect(postAuthDestination(state.user)).toBe('/onboarding/review');const html=render(h(AuthStatus));expect(html).toContain('Continue onboarding');expect(html).not.toContain('dashboard-grid');expect(postAuthDestination(user)).toBe('/');
});
it("does not render dashboard data for anonymous, unknown or failed sessions", () => {
 for(const current of [null,undefined]){state.user=current;expect(render(h(AuthStatus))).not.toContain('dashboard-grid');}
 state.user=null;expect(render(h(AuthStatus))).toContain('href="/login"');state.user=user;state.error='Session unavailable';const html=render(h(AuthStatus));expect(html).not.toContain('dashboard-grid');expect(html).toContain('Session unavailable');
});
