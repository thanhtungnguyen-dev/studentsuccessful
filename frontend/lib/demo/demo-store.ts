/**
 * Comprehensive Typed Demo Mode Store for `ApiClient`.
 *
 * Implements every method on `frontend/lib/api/client.ts` against OpenAPI types
 * (`schema.d.ts`), backed by `localStorage` with an in-memory fallback for SSR/tests.
 */

import type {
  Application,
  ApplicationCreate,
  ApplicationFilterStatus,
  ApplicationUpdate,
  Artifact,
  ArtifactCreate,
  ArtifactUpdate,
  CandidateProfile,
  CatalogItem,
  CatalogLocation,
  CurrentUser,
  Education,
  EducationCreate,
  EducationUpdate,
  Employment,
  EmploymentCreate,
  EmploymentUpdate,
  FitAnalysis,
  HealthLiveResponse,
  HealthReadyResponse,
  JobAlertInbox,
  JobAlertReadState,
  JobSearchParams,
  JobUserState,
  JobUserStateUpdate,
  LoginRequest,
  LoginResponse,
  LogoutResponse,
  Preferences,
  Profile,
  ProfileUpdate,
  Project,
  ProjectCreate,
  ProjectUpdate,
  PublicJob,
  PublicJobDetail,
  PublicJobSearch,
  RegisterRequest,
  RegisterResponse,
  Resume,
  ResumeAlignment,
  ResumeCreate,
  ResumeEvidence,
  ResumeExtractedText,
  ResumeImprovementPlan,
  ResumePrimaryVersionUpdate,
  ResumeTailoringDraft,
  ResumeTailoringReview,
  ResumeTailoringReviewCreate,
  ResumeTailoringReviewItemUpdate,
  ResumeUpdate,
  ResumeVersion,
  SavedJobSearch,
  SavedJobSearchCreate,
  SavedJobSearchUpdate,
  SkillGapAnalysis,
  SkillSelection,
  WorkAuthorization,
  WorkAuthorizationCreate,
  WorkAuthorizationUpdate,
} from "../api/client";
import type { components } from "../api/schema";
import { DEMO_API_STORAGE_KEY, DEMO_SESSION_STORAGE_KEY } from "./config";
import { loadDemoState, resetDemoState, saveDemoState } from "./demo-storage";

type CandidateSkillSourceRead = components["schemas"]["CandidateSkillSourceRead"];

interface PersistedDemoApiState {
  user: CurrentUser;
  profile: Profile;
  education: Education[];
  employment: Employment[];
  workAuthorizations: WorkAuthorization[];
  preferences: Preferences;
  skillsSelection: SkillSelection;
  projects: Project[];
  resumes: Resume[];
  resumeVersions: Record<string, ResumeVersion[]>;
  resumeEvidence: Record<string, ResumeEvidence[]>;
  resumeExtractedText: Record<string, ResumeExtractedText>;
  artifacts: Artifact[];
  savedJobIds: string[];
  hiddenJobIds: string[];
  viewedJobIds: Record<string, string>;
  savedSearches: SavedJobSearch[];
  alerts: JobAlertInbox["items"];
  applications: Application[];
  tailoringReviews: Record<string, ResumeTailoringReview>;
}

const ROLES_CATALOG: CatalogItem[] = [
  { id: "role-swe-intern", name: "Software Engineer Intern", slug: "software-engineer-intern", is_active: true, category: "Engineering" },
  { id: "role-fullstack-coop", name: "Full-Stack Developer Co-Op", slug: "full-stack-developer-coop", is_active: true, category: "Engineering" },
  { id: "role-systems-intern", name: "Systems Software Engineering Intern", slug: "systems-software-intern", is_active: true, category: "Systems" },
  { id: "role-backend-intern", name: "Backend / Distributed Systems Intern", slug: "backend-distributed-intern", is_active: true, category: "Engineering" },
  { id: "role-ml-systems", name: "Machine Learning Systems Intern", slug: "ml-systems-intern", is_active: true, category: "AI & ML" },
  { id: "role-graphics-intern", name: "Graphics Software Engineering Intern", slug: "graphics-software-intern", is_active: true, category: "Systems" },
];

const INDUSTRIES_CATALOG: CatalogItem[] = [
  { id: "ind-semiconductors", name: "Semiconductors & Systems", slug: "semiconductors-systems", is_active: true },
  { id: "ind-cloud", name: "Cloud & Distributed Computing", slug: "cloud-distributed", is_active: true },
  { id: "ind-ai", name: "AI & Accelerated Computing", slug: "ai-accelerated", is_active: true },
  { id: "ind-devtools", name: "Developer Tools & Infrastructure", slug: "developer-tools", is_active: true },
  { id: "ind-enterprise", name: "Enterprise Software", slug: "enterprise-software", is_active: true },
];

const COMPANIES_CATALOG: CatalogItem[] = [
  { id: "comp-amd", name: "AMD", slug: "amd", is_active: true },
  { id: "comp-nvidia", name: "NVIDIA", slug: "nvidia", is_active: true },
  { id: "comp-amazon", name: "Amazon", slug: "amazon", is_active: true },
  { id: "comp-ibm", name: "IBM", slug: "ibm", is_active: true },
];

const LOCATIONS_CATALOG: CatalogLocation[] = [
  { id: "loc-markham", city: "Markham", state_province: "ON", country_code: "CA" },
  { id: "loc-toronto", city: "Toronto", state_province: "ON", country_code: "CA" },
  { id: "loc-vancouver", city: "Vancouver", state_province: "BC", country_code: "CA" },
  { id: "loc-waterloo", city: "Waterloo", state_province: "ON", country_code: "CA" },
  { id: "loc-santaclara", city: "Santa Clara", state_province: "CA", country_code: "US" },
];

const SKILLS_CATALOG: CatalogItem[] = [
  { id: "skill-python", name: "Python", slug: "python", is_active: true, category: "Languages" },
  { id: "skill-c-cpp", name: "C/C++", slug: "c-cpp", is_active: true, category: "Languages" },
  { id: "skill-cpp", name: "C++", slug: "cpp", is_active: true, category: "Languages" },
  { id: "skill-react", name: "React", slug: "react", is_active: true, category: "Frontend" },
  { id: "skill-typescript", name: "TypeScript", slug: "typescript", is_active: true, category: "Languages" },
  { id: "skill-postgresql", name: "PostgreSQL", slug: "postgresql", is_active: true, category: "Databases" },
  { id: "skill-sql", name: "SQL", slug: "sql", is_active: true, category: "Databases" },
  { id: "skill-linux", name: "Linux", slug: "linux", is_active: true, category: "Systems" },
  { id: "skill-git", name: "Git", slug: "git", is_active: true, category: "Developer Tools" },
  { id: "skill-docker", name: "Docker", slug: "docker", is_active: true, category: "Infrastructure" },
  { id: "skill-java", name: "Java", slug: "java", is_active: true, category: "Languages" },
  { id: "skill-ds", name: "Data Structures", slug: "data-structures", is_active: true, category: "Computer Science" },
  { id: "skill-aws", name: "AWS", slug: "aws", is_active: true, category: "Cloud" },
  { id: "skill-swdev", name: "Software Development", slug: "software-development", is_active: true, category: "Engineering" },
  { id: "skill-prog", name: "Programming", slug: "programming", is_active: true, category: "Engineering" },
  { id: "skill-testing", name: "Testing", slug: "testing", is_active: true, category: "Quality" },
  { id: "skill-graphics", name: "Graphics", slug: "graphics", is_active: true, category: "Systems" },
  { id: "skill-debugging", name: "Debugging", slug: "debugging", is_active: true, category: "Systems" },
  { id: "skill-ml", name: "Machine Learning", slug: "machine-learning", is_active: true, category: "AI & ML" },
];

const SKILL_NAME_TO_ITEM = new Map<string, CatalogItem>(
  SKILLS_CATALOG.map((item) => [item.name.toLowerCase(), item])
);
const SKILL_ID_TO_ITEM = new Map<string, CatalogItem>(
  SKILLS_CATALOG.map((item) => [item.id, item])
);

function skillNameToId(name: string): string {
  return (
    SKILL_NAME_TO_ITEM.get(name.trim().toLowerCase())?.id ??
    `skill-${name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-")}`
  );
}

function skillIdToName(id: string): string {
  return SKILL_ID_TO_ITEM.get(id)?.name ?? id;
}

interface RichDemoJobSpec {
  id: string;
  title: string;
  description: string;
  company_id: string;
  company_name: string;
  role_id: string;
  role_name: string;
  employment_type: string;
  career_level: string;
  work_mode: string;
  source_name: string;
  application_url: string;
  posted_at: string;
  locations: string[];
  required_skills: { name: string; importance: string; description: string }[];
  education_requirements: PublicJobDetail["education_requirements"];
  eligibility_requirements: PublicJobDetail["eligibility_requirements"];
}

const DEMO_JOBS: RichDemoJobSpec[] = [
  {
    id: "amd-sw",
    title: "Short Term 2027 Software Engineering Intern/Co-Op",
    description:
      "AMD's Markham Software Engineering group is hiring 2027 Co-Op and Intern students (4–8 months, Req #91368). Work alongside AMD software engineers on C/C++ systems applications, Python diagnostic automation scripts, Linux software verification, and PostgreSQL telemetry pipelines.\n\nRequired Qualifications:\n• Strong foundation in C/C++ and Python programming\n• Experience working in Linux command-line and debugging environments\n• Familiarity with relational databases (PostgreSQL) and Git version control\n• Enrolled in a Bachelor's or Master's degree in Computer Science or Computer Engineering.",
    company_id: "comp-amd",
    company_name: "AMD",
    role_id: "role-swe-intern",
    role_name: "Software Engineer Intern",
    employment_type: "CO_OP",
    career_level: "INTERN",
    work_mode: "ON_SITE",
    source_name: "AMD Student Careers (Req #91368)",
    application_url: "https://careers.amd.com/students/jobs/91368?lang=en-us",
    posted_at: "2026-10-18T14:00:00Z",
    locations: ["Markham, ON, CA"],
    required_skills: [
      { name: "C/C++", importance: "REQUIRED", description: "Systems and driver application development in C/C++." },
      { name: "Python", importance: "REQUIRED", description: "Automation scripts and test harness tooling." },
      { name: "Linux", importance: "REQUIRED", description: "Linux command-line development and verification." },
      { name: "PostgreSQL", importance: "REQUIRED", description: "Relational database queries and telemetry storage." },
      { name: "Git", importance: "REQUIRED", description: "Collaborative source control and CI workflows." },
    ],
    education_requirements: [
      {
        id: "edu-req-amd-sw",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [
      {
        id: "elig-req-amd-sw",
        requirement_type: "WORK_AUTHORIZATION",
        value: "CA",
        description: "Authorized for co-op or internship employment in Canada.",
      },
    ],
  },
  {
    id: "nvidia-sw",
    title: "2027 Internships: Software Engineering",
    description:
      "NVIDIA is seeking 2027 Software Engineering Interns in Santa Clara, CA (Req #JR2023495). Interns build developer tools, cloud platform infrastructure, React observability interfaces, C++ systems libraries, and containerized Python workflows.\n\nWhat We Need To See:\n• Pursuing a BS/MS in Computer Science or Computer Engineering\n• Proficiency in Python and C++\n• Experience with web tooling (React), SQL databases, and Docker containers.",
    company_id: "comp-nvidia",
    company_name: "NVIDIA",
    role_id: "role-swe-intern",
    role_name: "Software Engineer Intern",
    employment_type: "INTERNSHIP",
    career_level: "INTERN",
    work_mode: "HYBRID",
    source_name: "NVIDIA University Recruiting (JR2023495)",
    application_url: "https://jobs.nvidia.com/careers/job/893397026205",
    posted_at: "2026-10-16T17:30:00Z",
    locations: ["Santa Clara, CA, US"],
    required_skills: [
      { name: "Python", importance: "REQUIRED", description: "Backend automation and platform services." },
      { name: "C++", importance: "REQUIRED", description: "High-performance systems software." },
      { name: "React", importance: "REQUIRED", description: "Internal developer platform dashboards." },
      { name: "SQL", importance: "REQUIRED", description: "Data querying and metrics storage." },
      { name: "Docker", importance: "PREFERRED", description: "Containerized build and test environments." },
    ],
    education_requirements: [
      {
        id: "edu-req-nvidia-sw",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [
      {
        id: "elig-req-nvidia-sw",
        requirement_type: "WORK_AUTHORIZATION",
        value: "US",
        description: "Eligible for US internship employment or J-1 visa sponsorship.",
      },
    ],
  },
  {
    id: "amazon-sde",
    title: "Software Development Engineer Intern — Summer 2027",
    description:
      "At Amazon Vancouver (Job ID 10553947), Software Development Engineer (SDE) Interns collaborate with experienced cross-disciplinary engineers to design, test, and operate distributed software services and customer-facing products.\n\nBasic Qualifications:\n• Currently enrolled in a Bachelor's or Master's degree in Computer Science or related field\n• Experience with Python or Java and strong Data Structures fundamentals\n• Familiarity with SQL and AWS cloud services.",
    company_id: "comp-amazon",
    company_name: "Amazon",
    role_id: "role-backend-intern",
    role_name: "Backend / Distributed Systems Intern",
    employment_type: "INTERNSHIP",
    career_level: "INTERN",
    work_mode: "ON_SITE",
    source_name: "Amazon University Talent (Job #10553947)",
    application_url:
      "https://amazon.jobs/en/jobs/10553947/software-development-engineer-intern-summer-2027-can",
    posted_at: "2026-10-12T10:15:00Z",
    locations: ["Vancouver, BC, CA"],
    required_skills: [
      { name: "Python", importance: "REQUIRED", description: "Object-oriented service implementation." },
      { name: "Java", importance: "PREFERRED", description: "Backend service development in Java." },
      { name: "Data Structures", importance: "REQUIRED", description: "Algorithmic problem solving and complexity analysis." },
      { name: "AWS", importance: "PREFERRED", description: "Cloud infrastructure and distributed services." },
      { name: "SQL", importance: "REQUIRED", description: "Relational data modeling and queries." },
    ],
    education_requirements: [
      {
        id: "edu-req-amazon-sde",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [
      {
        id: "elig-req-amazon-sde",
        requirement_type: "WORK_AUTHORIZATION",
        value: "CA",
        description: "Authorized for internship work in Canada.",
      },
    ],
  },
  {
    id: "ibm-dev",
    title: "Software Developer Intern 2027",
    description:
      "Contribute to enterprise software development, automated verification, and cloud services at IBM Software in Markham (Req #129661).\n\nRequired Technical Expertise:\n• Demonstrated Software Development and Programming fundamentals\n• Experience writing unit and integration Testing suites.",
    company_id: "comp-ibm",
    company_name: "IBM",
    role_id: "role-swe-intern",
    role_name: "Software Engineer Intern",
    employment_type: "INTERNSHIP",
    career_level: "INTERN",
    work_mode: "HYBRID",
    source_name: "IBM Early Professional Careers (Req #129661)",
    application_url:
      "https://careers.ibm.com/en_US/careers/JobDetail/Software-Developer-Intern-2027/129661",
    posted_at: "2026-10-08T09:00:00Z",
    locations: ["Markham, ON, CA"],
    required_skills: [
      { name: "Software Development", importance: "REQUIRED", description: "Iterative software design and implementation." },
      { name: "Programming", importance: "REQUIRED", description: "Clean, maintainable code in modern languages." },
      { name: "Testing", importance: "REQUIRED", description: "Automated unit and integration verification." },
    ],
    education_requirements: [
      {
        id: "edu-req-ibm-dev",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [],
  },
  {
    id: "amd-graphics",
    title: "Short Term 2027 Graphics Software Engineering Intern/Co-Op",
    description:
      "Contribute to graphics driver development, rendering pipelines, and low-level systems debugging with AMD Radeon engineering in Markham (Req #91359).\n\nRequirements:\n• Strong C++ programming and systems Debugging skills\n• Linux development experience\n• Coursework or project background in computer Graphics or GPU architectures.",
    company_id: "comp-amd",
    company_name: "AMD",
    role_id: "role-graphics-intern",
    role_name: "Graphics Software Engineering Intern",
    employment_type: "CO_OP",
    career_level: "INTERN",
    work_mode: "ON_SITE",
    source_name: "AMD Student Careers (Req #91359)",
    application_url: "https://careers.amd.com/careers-home/jobs/91359?icims=1",
    posted_at: "2026-10-15T13:20:00Z",
    locations: ["Markham, ON, CA"],
    required_skills: [
      { name: "C++", importance: "REQUIRED", description: "Low-level C++ driver and runtime programming." },
      { name: "Graphics", importance: "REQUIRED", description: "Rendering pipelines or GPU programming fundamentals." },
      { name: "Linux", importance: "REQUIRED", description: "Linux kernel/user-space environment." },
      { name: "Debugging", importance: "REQUIRED", description: "Root-cause debugging with gdb or profiling tools." },
    ],
    education_requirements: [
      {
        id: "edu-req-amd-gfx",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [],
  },
  {
    id: "amazon-ml",
    title: "ML Systems Software Development Engineer Intern — 2027",
    description:
      "Work on machine learning infrastructure, developer observability tools, and high-throughput systems at Amazon Annapurna Labs in Toronto (Job ID 10538066).\n\nRequirements:\n• Proficiency in Python and C++\n• Experience with React and TypeScript for developer observability tooling\n• Exposure to Machine Learning frameworks or systems benchmarking.",
    company_id: "comp-amazon",
    company_name: "Amazon",
    role_id: "role-ml-systems",
    role_name: "Machine Learning Systems Intern",
    employment_type: "INTERNSHIP",
    career_level: "INTERN",
    work_mode: "HYBRID",
    source_name: "Amazon Annapurna Labs (Job #10538066)",
    application_url:
      "https://www.amazon.jobs/en/jobs/10538066/ml-systems-software-development-engineer-intern-annapurna-labs-2027",
    posted_at: "2026-10-19T11:45:00Z",
    locations: ["Toronto, ON, CA"],
    required_skills: [
      { name: "Python", importance: "REQUIRED", description: "ML benchmarking and orchestration scripts." },
      { name: "C++", importance: "REQUIRED", description: "High-throughput systems runtime components." },
      { name: "Machine Learning", importance: "REQUIRED", description: "ML model execution and profiling concepts." },
      { name: "React", importance: "PREFERRED", description: "Developer observability web interfaces." },
      { name: "TypeScript", importance: "PREFERRED", description: "Typed frontend tooling." },
    ],
    education_requirements: [
      {
        id: "edu-req-amazon-ml",
        degree_level: "BS",
        target_grad_start: "2027",
        target_grad_end: "2029",
      },
    ],
    eligibility_requirements: [],
  },
];

let memoryApiState: PersistedDemoApiState | null = null;
let memorySessionActive = false;

export function isDemoSessionActive(): boolean {
  if (typeof window === "undefined") {
    return memorySessionActive;
  }
  try {
    const val =
      window.sessionStorage.getItem(DEMO_SESSION_STORAGE_KEY) ||
      window.localStorage.getItem(DEMO_SESSION_STORAGE_KEY);
    return val === "true" || memorySessionActive;
  } catch {
    return memorySessionActive;
  }
}

export function activateDemoSession(): void {
  memorySessionActive = true;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(DEMO_SESSION_STORAGE_KEY, "true");
    window.localStorage.setItem(DEMO_SESSION_STORAGE_KEY, "true");
    document.cookie = "ss_csrf=demo-csrf-token; path=/; SameSite=Lax";
  } catch {
    // Ignore storage errors
  }
}

export function endDemoSession(): void {
  memorySessionActive = false;
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
    window.localStorage.removeItem(DEMO_SESSION_STORAGE_KEY);
  } catch {
    // Ignore storage errors
  }
}

function toPublicJob(
  spec: RichDemoJobSpec,
  saved: boolean,
  hidden: boolean,
  viewedAt: string | null
): PublicJob {
  return {
    id: spec.id,
    title: spec.title,
    description: spec.description,
    company_id: spec.company_id,
    company_name: spec.company_name,
    role_id: spec.role_id,
    role_name: spec.role_name,
    employment_type: spec.employment_type,
    career_level: spec.career_level,
    work_mode: spec.work_mode,
    source_name: spec.source_name,
    application_url: spec.application_url,
    posted_at: spec.posted_at,
    discovered_at: spec.posted_at,
    first_seen_at: spec.posted_at,
    last_seen_at: "2026-10-22T12:00:00Z",
    last_verified_at: "2026-10-22T12:00:00Z",
    canonical_updated_at: "2026-10-22T12:00:00Z",
    lifecycle: "ACTIVE",
    saved,
    hidden,
    viewed_at: viewedAt,
    unseen: viewedAt === null,
    matched_filters: spec.locations,
  };
}

function toPublicJobDetail(
  spec: RichDemoJobSpec,
  saved: boolean,
  hidden: boolean,
  viewedAt: string | null
): PublicJobDetail {
  const base = toPublicJob(spec, saved, hidden, viewedAt);
  return {
    ...base,
    locations: spec.locations,
    skill_requirements: spec.required_skills.map((req) => {
      const catItem = SKILL_NAME_TO_ITEM.get(req.name.toLowerCase());
      return {
        skill_id: catItem?.id ?? skillNameToId(req.name),
        skill_name: req.name,
        skill_category: catItem?.category ?? "Engineering",
        importance: req.importance,
        description: req.description,
      };
    }),
    education_requirements: spec.education_requirements,
    eligibility_requirements: spec.eligibility_requirements,
  };
}

function buildEvidenceForSkillNames(
  resumeVersionId: string,
  skillNames: string[]
): ResumeEvidence[] {
  return skillNames.map((skillName, index) => {
    const catItem = SKILL_NAME_TO_ITEM.get(skillName.toLowerCase());
    const skillId = catItem?.id ?? skillNameToId(skillName);
    const category: ResumeEvidence["category"] =
      index < 4 ? "EXPERIENCE" : index < 8 ? "PROJECTS" : "SKILLS";
    const sectionHeader =
      category === "EXPERIENCE"
        ? "Work Experience"
        : category === "PROJECTS"
          ? "Technical Projects"
          : "Technical Skills";
    return {
      id: `ev-${resumeVersionId}-${index + 1}`,
      resume_version_id: resumeVersionId,
      ordinal: index + 1,
      category,
      section_header: sectionHeader,
      bullet_text:
        category === "EXPERIENCE"
          ? `Engineered production-grade ${skillName} modules in Waterloo Systems Lab, reducing diagnostic query latency by 38% across 250k test rows.`
          : category === "PROJECTS"
            ? `Built and verified ${skillName} components in TraceFlow and CoOpMap with 99.4% automated CI test coverage.`
            : `Proficient in ${skillName} across undergraduate coursework, co-op projects, and lab teaching.`,
      recognized_skills: [
        {
          skill_id: skillId,
          name: catItem?.name ?? skillName,
          parser_confidence: "HIGH",
        },
      ],
    };
  });
}

function createInitialApiState(): PersistedDemoApiState {
  const landing = loadDemoState();

  const user: CurrentUser = {
    id: "user-demo-alex-2027",
    email: landing.profile.email || "alex.rivera@university.edu",
    is_active: true,
    created_at: "2026-09-15T12:00:00Z",
    onboarding_completed_at: "2026-10-01T14:30:00Z",
  };

  const profile: Profile = {
    legal_first_name: "Alex",
    legal_last_name: "Rivera",
    legal_middle_name: null,
    preferred_name: landing.profile.preferredName || "Alex",
    phone_number: "+1 (519) 555-0194",
    address_street: "200 University Ave W",
    address_city: "Waterloo",
    address_state_province: "ON",
    address_postal_code: "N2L 3G1",
    address_country_code: "CA",
    linkedin_url: "https://www.linkedin.com/in/alex-rivera-demo",
    github_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
    portfolio_url: "https://studentsuccessful.example/alex-rivera",
  };

  const education: Education[] = [
    {
      id: "edu-waterloo-cs",
      institution_name: "University of Waterloo",
      degree_level: "BS",
      major: "Computer Science (Honours Co-Op)",
      minor: "Systems & Software Engineering",
      study_year: "YEAR_2",
      start_date: "2025-09-01",
      expected_grad_month: 4,
      expected_grad_year: 2028,
      gpa_value: "3.85",
      gpa_scale: "4.00",
      gpa_include_on_apps: true,
      is_primary: true,
      created_at: "2026-09-15T12:10:00Z",
      updated_at: "2026-10-15T09:00:00Z",
    },
  ];

  const employment: Employment[] = [
    {
      id: "emp-waterloo-ta",
      employer_name: "University of Waterloo — School of Computer Science",
      job_title: "Undergraduate Teaching Assistant (Data Structures & C++)",
      location: "Waterloo, ON, Canada",
      start_date: "2026-09-01",
      end_date: null,
      currently_employed: true,
      description:
        "Lead weekly C++ and Python lab sections for 60+ undergraduate students covering memory management, graph algorithms, gdb debugging, and automated unit testing harnesses.",
      created_at: "2026-09-15T12:15:00Z",
      updated_at: "2026-10-18T11:00:00Z",
    },
    {
      id: "emp-systems-lab",
      employer_name: "Waterloo Systems & Telemetry Lab",
      job_title: "Undergraduate Systems Software Researcher (Co-Op)",
      location: "Waterloo, ON, Canada",
      start_date: "2026-05-01",
      end_date: "2026-08-28",
      currently_employed: false,
      description:
        "Engineered a Linux process telemetry agent in C/C++ and Python that streamed diagnostic events into PostgreSQL, cutting query latency by 38% across 250k test rows.",
      created_at: "2026-09-15T12:18:00Z",
      updated_at: "2026-10-10T15:00:00Z",
    },
  ];

  const workAuthorizations: WorkAuthorization[] = [
    {
      id: "wa-canada",
      country_code: "CA",
      authorization_status: "CITIZEN",
      requires_current_sponsorship: false,
      requires_future_sponsorship: false,
      notes: "Authorized for all Canadian 4-month and 8-month Co-Op and internship terms.",
      last_confirmed_at: "2026-10-01T12:00:00Z",
      created_at: "2026-09-15T12:20:00Z",
      updated_at: "2026-10-01T12:00:00Z",
    },
    {
      id: "wa-us",
      country_code: "US",
      authorization_status: "STUDENT_VISA_CPT_OPT",
      requires_current_sponsorship: true,
      requires_future_sponsorship: true,
      notes: "Eligible for US J-1 Intern Visa sponsorship through university co-op enrollment.",
      last_confirmed_at: "2026-10-01T12:00:00Z",
      created_at: "2026-09-15T12:22:00Z",
      updated_at: "2026-10-01T12:00:00Z",
    },
  ];

  const initialSkillIds: string[] = [];
  const initialCustomSkills: string[] = [];
  for (const s of landing.profile.skills) {
    const cat = SKILL_NAME_TO_ITEM.get(s.toLowerCase());
    if (cat) {
      if (!initialSkillIds.includes(cat.id)) initialSkillIds.push(cat.id);
    } else if (!initialCustomSkills.includes(s)) {
      initialCustomSkills.push(s);
    }
  }

  const skillsSelection: SkillSelection = {
    skill_ids: initialSkillIds,
    custom_values: initialCustomSkills,
  };

  const preferences: Preferences = {
    role_ids: ["role-swe-intern", "role-fullstack-coop", "role-systems-intern"],
    industry_ids: ["ind-semiconductors", "ind-cloud", "ind-ai", "ind-devtools"],
    location_ids: ["loc-markham", "loc-toronto", "loc-vancouver", "loc-santaclara"],
    company_ids: ["comp-amd", "comp-nvidia", "comp-amazon", "comp-ibm"],
    skill_ids: initialSkillIds.slice(0, 8),
    work_modes: ["ON_SITE", "HYBRID", "REMOTE"],
    employment_types: ["INTERNSHIP", "CO_OP"],
    custom_values: [],
  };

  const projects: Project[] = [
    {
      id: "proj-traceflow",
      title: "TraceFlow — Linux Systems & PostgreSQL Telemetry Agent",
      description:
        "Built a lightweight Linux daemon in C/C++ with Python CLI tooling that collects process metrics and indexes time-series diagnostic logs into PostgreSQL. Reduced query latency across 250k rows by 38%.",
      technologies: {
        skill_ids: [
          skillNameToId("C/C++"),
          skillNameToId("Python"),
          skillNameToId("Linux"),
          skillNameToId("PostgreSQL"),
          skillNameToId("Git"),
          skillNameToId("Debugging"),
        ],
        custom_values: [],
      },
      project_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      repository_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      created_at: "2026-09-15T12:30:00Z",
      updated_at: "2026-10-18T14:00:00Z",
    },
    {
      id: "proj-coopmap",
      title: "CoOpMap — Full-Stack Course & Requirement Visualizer",
      description:
        "Designed an interactive prerequisite and skill-mapping web application in React, TypeScript, Python, and PostgreSQL for undergraduate CS students with 99.4% CI test pass rate.",
      technologies: {
        skill_ids: [
          skillNameToId("React"),
          skillNameToId("TypeScript"),
          skillNameToId("Python"),
          skillNameToId("SQL"),
          skillNameToId("PostgreSQL"),
          skillNameToId("Testing"),
          skillNameToId("Software Development"),
        ],
        custom_values: [],
      },
      project_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      repository_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      created_at: "2026-09-15T12:32:00Z",
      updated_at: "2026-10-12T10:00:00Z",
    },
    {
      id: "proj-algobench",
      title: "AlgoBench — C++ Data Structures & Automated Grading Harness",
      description:
        "Created deterministic C++ and Python benchmark harnesses to test student graph and memory-management submissions with clear edge-case diagnostics.",
      technologies: {
        skill_ids: [
          skillNameToId("Data Structures"),
          skillNameToId("C++"),
          skillNameToId("Python"),
          skillNameToId("Programming"),
          skillNameToId("Debugging"),
          skillNameToId("Testing"),
        ],
        custom_values: [],
      },
      project_url: null,
      repository_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      created_at: "2026-09-20T16:00:00Z",
      updated_at: "2026-10-20T09:30:00Z",
    },
  ];

  const resumes: Resume[] = [
    {
      id: "resume-v2",
      title: "Resume v2 — Systems & Full-Stack Co-Op",
      created_at: "2026-10-15T10:00:00Z",
    },
    {
      id: "resume-v1",
      title: "Resume v1 — General Software Engineering",
      created_at: "2026-10-01T10:00:00Z",
    },
  ];

  const v2Version: ResumeVersion = {
    id: "version-v2",
    resume_id: "resume-v2",
    version_number: 2,
    file_format: "PDF",
    file_size_bytes: 184320,
    file_hash_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    is_primary_active: true,
    parse_status: "PARSED_SUCCESS",
    created_at: "2026-10-21T15:59:30Z",
  };

  const v1Version: ResumeVersion = {
    id: "version-v1",
    resume_id: "resume-v1",
    version_number: 1,
    file_format: "PDF",
    file_size_bytes: 162400,
    file_hash_sha256: "a1b2c3d498fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b111",
    is_primary_active: true,
    parse_status: "PARSED_SUCCESS",
    created_at: "2026-10-12T14:19:45Z",
  };

  const resumeVersions: Record<string, ResumeVersion[]> = {
    "resume-v2": [v2Version],
    "resume-v1": [v1Version],
  };

  const v2Skills = landing.resumes.find((r) => r.id === "v2")?.includedSkills ?? [
    "C/C++",
    "C++",
    "Python",
    "Linux",
    "PostgreSQL",
    "SQL",
    "Git",
    "React",
    "TypeScript",
    "Debugging",
    "Testing",
    "Software Development",
    "Programming",
  ];

  const v1Skills = landing.resumes.find((r) => r.id === "v1")?.includedSkills ?? [
    "Python",
    "React",
    "TypeScript",
    "SQL",
    "PostgreSQL",
    "Data Structures",
    "Software Development",
    "Programming",
    "Testing",
    "Git",
  ];

  const resumeEvidence: Record<string, ResumeEvidence[]> = {
    "version-v2": buildEvidenceForSkillNames("version-v2", v2Skills),
    "version-v1": buildEvidenceForSkillNames("version-v1", v1Skills),
  };

  const resumeExtractedText: Record<string, ResumeExtractedText> = {
    "version-v2": {
      raw_extracted_text:
        "ALEX RIVERA — B.Sc. Honours Computer Science (Co-Op), University of Waterloo (GPA 3.85/4.00)\n" +
        "TECHNICAL SKILLS: C/C++, C++, Python, Linux, PostgreSQL, SQL, Git, React, TypeScript, Debugging, Testing\n" +
        "EXPERIENCE:\n" +
        "• Undergraduate Systems Software Researcher, Waterloo Systems Lab: Engineered a Linux telemetry daemon in C/C++ and Python indexing 250k+ rows into PostgreSQL (-38% query latency).\n" +
        "• Undergraduate Teaching Assistant (Data Structures & C++): Led weekly lab debugging sessions for 60+ CS students.\n" +
        "PROJECTS:\n" +
        "• TraceFlow (C/C++, Python, Linux, PostgreSQL, Git): Systems telemetry collector and automated verification CLI.\n" +
        "• CoOpMap (React, TypeScript, Python, PostgreSQL): Full-stack course & requirement visualizer.",
    },
    "version-v1": {
      raw_extracted_text:
        "ALEX RIVERA — B.Sc. Honours Computer Science (Co-Op), University of Waterloo\n" +
        "TECHNICAL SKILLS: Python, React, TypeScript, SQL, PostgreSQL, Data Structures, Git, Testing\n" +
        "PROJECTS & EXPERIENCE:\n" +
        "• CoOpMap — Full-Stack Course & Requirement Visualizer (React, TypeScript, Python, PostgreSQL): Built interactive web app used by 180+ students with 99.4% test pass rate.\n" +
        "• Undergraduate Teaching Assistant — Data Structures & Algorithms: Mentored 60+ students and wrote automated Python grading suites.",
    },
  };

  const artifacts: Artifact[] = [
    {
      id: "art-github-portfolio",
      artifact_type: "RESUME",
      title: "GitHub Systems & Full-Stack Portfolio",
      external_url: "https://github.com/thanhtungnguyen-dev/studentsuccessful",
      created_at: "2026-09-20T12:00:00Z",
      updated_at: "2026-10-18T12:00:00Z",
    },
    {
      id: "art-coopmap-report",
      artifact_type: "RESUME",
      title: "TraceFlow & CoOpMap Technical Write-Up",
      external_url: "https://studentsuccessful.example/portfolio/alex-rivera",
      created_at: "2026-10-02T15:30:00Z",
      updated_at: "2026-10-19T09:15:00Z",
    },
  ];

  const savedSearches: SavedJobSearch[] = [
    {
      id: "search-canada-systems",
      name: "2027 Canada Systems & Backend Co-Op (C++ / Python)",
      criteria: {
        roles: ["Software Engineer Intern", "Systems Software Engineering Intern"],
        countries: ["CA"],
        regions: ["ON", "BC"],
        cities: ["Markham", "Toronto", "Vancouver"],
        job_types: ["CO_OP", "INTERNSHIP"],
        work_modes: ["ON_SITE", "HYBRID"],
        recency: "7d",
        keyword: "Software Engineering",
        company: null,
        requirement: "Python",
      },
      alert_mode: "INSTANT",
      alert_enabled_at: "2026-10-05T10:00:00Z",
      created_at: "2026-10-05T10:00:00Z",
      updated_at: "2026-10-22T08:00:00Z",
    },
    {
      id: "search-us-summer",
      name: "Summer 2027 US & Hybrid SWE Internships",
      criteria: {
        roles: ["Software Engineer Intern"],
        countries: ["US", "CA"],
        regions: ["CA", "ON"],
        cities: ["Santa Clara", "Toronto"],
        job_types: ["INTERNSHIP"],
        work_modes: ["HYBRID", "ON_SITE"],
        recency: "all",
        keyword: "C++",
        company: null,
        requirement: null,
      },
      alert_mode: "DAILY_DIGEST",
      alert_enabled_at: "2026-10-10T14:00:00Z",
      created_at: "2026-10-10T14:00:00Z",
      updated_at: "2026-10-22T08:00:00Z",
    },
  ];

  const alerts: JobAlertInbox["items"] = [
    {
      id: "alert-amd-sw",
      canonical_job_id: "amd-sw",
      saved_search_id: "search-canada-systems",
      saved_search_name: "2027 Canada Systems & Backend Co-Op (C++ / Python)",
      delivery_mode: "INSTANT",
      scheduled_for: "2026-10-22T09:30:00Z",
      created_at: "2026-10-22T09:30:00Z",
      delivered_at: "2026-10-22T09:30:05Z",
      read_at: null,
      title: DEMO_JOBS[0].title,
      company_name: DEMO_JOBS[0].company_name,
      employment_type: DEMO_JOBS[0].employment_type,
      work_mode: DEMO_JOBS[0].work_mode,
      application_url: DEMO_JOBS[0].application_url,
      first_seen_at: DEMO_JOBS[0].posted_at,
      locations: DEMO_JOBS[0].locations,
    },
    {
      id: "alert-amazon-ml",
      canonical_job_id: "amazon-ml",
      saved_search_id: "search-us-summer",
      saved_search_name: "Summer 2027 US & Hybrid SWE Internships",
      delivery_mode: "DAILY_DIGEST",
      scheduled_for: "2026-10-21T14:15:00Z",
      created_at: "2026-10-21T14:15:00Z",
      delivered_at: "2026-10-21T14:15:02Z",
      read_at: null,
      title: DEMO_JOBS[5].title,
      company_name: DEMO_JOBS[5].company_name,
      employment_type: DEMO_JOBS[5].employment_type,
      work_mode: DEMO_JOBS[5].work_mode,
      application_url: DEMO_JOBS[5].application_url,
      first_seen_at: DEMO_JOBS[5].posted_at,
      locations: DEMO_JOBS[5].locations,
    },
  ];

  const applications: Application[] = [
    {
      id: "app-amd-sw",
      canonical_job_id: "amd-sw",
      job_title: DEMO_JOBS[0].title,
      company_name: DEMO_JOBS[0].company_name,
      application_url: DEMO_JOBS[0].application_url,
      job_lifecycle: "ACTIVE",
      current_status: "APPLIED",
      resume_version_id: "version-v2",
      resume_title: "Resume v2 — Systems & Full-Stack Co-Op",
      resume_version_number: 2,
      applied_at: "2026-10-18T16:20:00Z",
      notes:
        "Applied via official AMD Student Careers portal (Req #91368) using Resume v2. Matched all 5 core requirements (C/C++, Python, Linux, PostgreSQL, Git).",
      version: 1,
      created_at: "2026-10-18T16:20:00Z",
      updated_at: "2026-10-18T16:20:00Z",
      history: [
        {
          id: "hist-amd-1",
          previous_status: null,
          new_status: "APPLIED",
          notes: "Submitted online application with Resume v2.",
          transitioned_at: "2026-10-18T16:20:00Z",
        },
      ],
    },
    {
      id: "app-nvidia-sw",
      canonical_job_id: "nvidia-sw",
      job_title: DEMO_JOBS[1].title,
      company_name: DEMO_JOBS[1].company_name,
      application_url: DEMO_JOBS[1].application_url,
      job_lifecycle: "ACTIVE",
      current_status: "INTERVIEW",
      resume_version_id: "version-v2",
      resume_title: "Resume v2 — Systems & Full-Stack Co-Op",
      resume_version_number: 2,
      applied_at: "2026-10-15T18:00:00Z",
      notes:
        "First-round technical screen scheduled with NVIDIA Santa Clara platform team. Reviewing C++ memory model and Docker containerization.",
      version: 2,
      created_at: "2026-10-15T18:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
      history: [
        {
          id: "hist-nv-1",
          previous_status: null,
          new_status: "APPLIED",
          notes: "Applied via NVIDIA University Recruiting.",
          transitioned_at: "2026-10-15T18:00:00Z",
        },
        {
          id: "hist-nv-2",
          previous_status: "APPLIED",
          new_status: "INTERVIEW",
          notes: "Invited to 45-minute technical interview.",
          transitioned_at: "2026-10-20T10:00:00Z",
        },
      ],
    },
    {
      id: "app-amazon-sde",
      canonical_job_id: "amazon-sde",
      job_title: DEMO_JOBS[2].title,
      company_name: DEMO_JOBS[2].company_name,
      application_url: DEMO_JOBS[2].application_url,
      job_lifecycle: "ACTIVE",
      current_status: "APPLIED",
      resume_version_id: "version-v1",
      resume_title: "Resume v1 — General Software Engineering",
      resume_version_number: 1,
      applied_at: "2026-10-11T12:00:00Z",
      notes:
        "Completed online coding assessment for Amazon Vancouver Summer 2027 SDE Intern. Highlighting Data Structures TA experience.",
      version: 1,
      created_at: "2026-10-11T12:00:00Z",
      updated_at: "2026-10-14T09:00:00Z",
      history: [
        {
          id: "hist-amz-1",
          previous_status: null,
          new_status: "APPLIED",
          notes: "Submitted application with Resume v1.",
          transitioned_at: "2026-10-11T12:00:00Z",
        },
      ],
    },
    {
      id: "app-ibm-dev",
      canonical_job_id: "ibm-dev",
      job_title: DEMO_JOBS[3].title,
      company_name: DEMO_JOBS[3].company_name,
      application_url: DEMO_JOBS[3].application_url,
      job_lifecycle: "ACTIVE",
      current_status: "OFFER",
      resume_version_id: "version-v1",
      resume_title: "Resume v1 — General Software Engineering",
      resume_version_number: 1,
      applied_at: "2026-10-04T15:00:00Z",
      notes:
        "Received internship offer from IBM Software Markham (Req #129661)! Reviewing start-date details with university co-op advisor.",
      version: 3,
      created_at: "2026-10-04T15:00:00Z",
      updated_at: "2026-10-21T17:00:00Z",
      history: [
        {
          id: "hist-ibm-1",
          previous_status: null,
          new_status: "APPLIED",
          notes: "Applied on IBM Early Professional portal.",
          transitioned_at: "2026-10-04T15:00:00Z",
        },
        {
          id: "hist-ibm-2",
          previous_status: "APPLIED",
          new_status: "INTERVIEW",
          notes: "Completed panel interview with Markham cloud team.",
          transitioned_at: "2026-10-12T15:00:00Z",
        },
        {
          id: "hist-ibm-3",
          previous_status: "INTERVIEW",
          new_status: "OFFER",
          notes: "Received written internship offer!",
          transitioned_at: "2026-10-21T17:00:00Z",
        },
      ],
    },
  ];

  return {
    user,
    profile,
    education,
    employment,
    workAuthorizations,
    preferences,
    skillsSelection,
    projects,
    resumes,
    resumeVersions,
    resumeEvidence,
    resumeExtractedText,
    artifacts,
    savedJobIds: landing.savedJobIds.length
      ? landing.savedJobIds
      : ["amd-sw", "nvidia-sw", "amazon-ml"],
    hiddenJobIds: [],
    viewedJobIds: { "amd-sw": "2026-10-22T10:00:00Z" },
    savedSearches,
    alerts,
    applications,
    tailoringReviews: {},
  };
}

function loadApiState(): PersistedDemoApiState {
  if (typeof window === "undefined") {
    if (!memoryApiState) {
      memoryApiState = createInitialApiState();
    }
    return memoryApiState;
  }

  try {
    const raw = window.localStorage.getItem(DEMO_API_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as PersistedDemoApiState;
      if (parsed && parsed.user && parsed.profile && Array.isArray(parsed.resumes)) {
        memoryApiState = parsed;
        return parsed;
      }
    }
  } catch {
    if (memoryApiState) return memoryApiState;
  }

  const fresh = createInitialApiState();
  saveApiState(fresh);
  return fresh;
}

function saveApiState(state: PersistedDemoApiState): void {
  memoryApiState = state;
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(DEMO_API_STORAGE_KEY, JSON.stringify(state));
    // Sync skill names and saved jobs back to landing page state
    const landing = loadDemoState();
    const skillNames = [
      ...(state.skillsSelection.skill_ids ?? []).map(skillIdToName),
      ...(state.skillsSelection.custom_values ?? []),
    ];
    saveDemoState({
      ...landing,
      profile: {
        ...landing.profile,
        preferredName: state.profile.preferred_name || landing.profile.preferredName,
        fullName: `${state.profile.legal_first_name} ${state.profile.legal_last_name}`.trim(),
        skills: skillNames,
      },
      savedJobIds: state.savedJobIds,
    });
  } catch {
    // Ignore storage errors
  }
}

export function resetDemoApiState(): void {
  resetDemoState();
  const fresh = createInitialApiState();
  memoryApiState = fresh;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(DEMO_API_STORAGE_KEY);
      window.localStorage.setItem(DEMO_API_STORAGE_KEY, JSON.stringify(fresh));
    } catch {
      // Ignore storage errors
    }
  }
}

function findJobSpec(jobId: string): RichDemoJobSpec {
  return (
    DEMO_JOBS.find(
      (j) =>
        j.id === jobId ||
        (jobId === "1001" && j.id === "amd-sw") ||
        (jobId === "1002" && j.id === "nvidia-sw") ||
        (jobId === "1003" && j.id === "amazon-sde") ||
        (jobId === "1004" && j.id === "ibm-dev") ||
        (jobId === "1005" && j.id === "amd-graphics") ||
        (jobId === "1006" && j.id === "amazon-ml")
    ) ?? DEMO_JOBS[0]
  );
}

function resolveResumeVersion(
  state: PersistedDemoApiState,
  resumeVersionId?: string | null
): { resume: Resume; version: ResumeVersion; evidence: ResumeEvidence[] } {
  for (const res of state.resumes) {
    const versions = state.resumeVersions[res.id] ?? [];
    for (const ver of versions) {
      if (ver.id === resumeVersionId || res.id === resumeVersionId) {
        return {
          resume: res,
          version: ver,
          evidence: state.resumeEvidence[ver.id] ?? [],
        };
      }
    }
  }
  const fallbackResume = state.resumes[0];
  const fallbackVersion = (state.resumeVersions[fallbackResume.id] ?? [])[0];
  return {
    resume: fallbackResume,
    version: fallbackVersion,
    evidence: state.resumeEvidence[fallbackVersion.id] ?? [],
  };
}

function getAllCandidateSkillSources(
  state: PersistedDemoApiState
): Map<string, CandidateSkillSourceRead[]> {
  const bySkillId = new Map<string, CandidateSkillSourceRead[]>();

  const pushSource = (skillId: string, source: CandidateSkillSourceRead) => {
    const list = bySkillId.get(skillId) ?? [];
    list.push(source);
    bySkillId.set(skillId, list);
  };

  for (const skillId of state.skillsSelection.skill_ids ?? []) {
    pushSource(skillId, {
      source_type: "CONFIRMED_BY_USER",
      source_id: `user-skill-${skillId}`,
    });
  }

  for (const proj of state.projects) {
    for (const skillId of proj.technologies?.skill_ids ?? []) {
      pushSource(skillId, {
        source_type: "PROJECT",
        source_id: proj.id,
        project_id: proj.id,
        project_title: proj.title,
      });
    }
  }

  for (const res of state.resumes) {
    const versions = state.resumeVersions[res.id] ?? [];
    for (const ver of versions) {
      if (!ver.is_primary_active) continue;
      const evItems = state.resumeEvidence[ver.id] ?? [];
      for (const ev of evItems) {
        for (const rec of ev.recognized_skills ?? []) {
          pushSource(rec.skill_id, {
            source_type: "RESUME_EVIDENCE",
            source_id: ev.id,
            resume_id: res.id,
            resume_title: res.title,
            resume_version_id: ver.id,
            resume_version_number: ver.version_number,
            evidence_ordinal: ev.ordinal,
            evidence_category: ev.category,
            evidence_section_header: ev.section_header ?? null,
            parser_confidence: rec.parser_confidence,
          });
        }
      }
    }
  }

  return bySkillId;
}

export const demoStore = {
  async register(payload: RegisterRequest): Promise<RegisterResponse> {
    const state = loadApiState();
    state.user = {
      ...state.user,
      email: payload.email.trim() || state.user.email,
      onboarding_completed_at:
        state.user.onboarding_completed_at ?? new Date().toISOString(),
    };
    saveApiState(state);
    activateDemoSession();
    return {
      user: state.user,
      csrf_token: "demo-csrf-token",
    };
  },

  async login(payload: LoginRequest): Promise<LoginResponse> {
    const state = loadApiState();
    if (payload.email?.trim()) {
      state.user = {
        ...state.user,
        email: payload.email.trim(),
      };
      saveApiState(state);
    }
    activateDemoSession();
    return {
      user: state.user,
      csrf_token: "demo-csrf-token",
    };
  },

  async getCurrentUser(): Promise<CurrentUser | null> {
    // Never sign a user in merely because they visited a workspace URL.
    // A demo session starts only through an explicit entry action.
    if (!isDemoSessionActive()) return null;
    return loadApiState().user;
  },

  async completeOnboarding(): Promise<CurrentUser> {
    const state = loadApiState();
    state.user = {
      ...state.user,
      onboarding_completed_at: new Date().toISOString(),
    };
    saveApiState(state);
    activateDemoSession();
    return state.user;
  },

  async logout(): Promise<LogoutResponse> {
    endDemoSession();
    return { message: "Successfully logged out" };
  },

  async listArtifacts(): Promise<Artifact[]> {
    return loadApiState().artifacts;
  },

  async createArtifact(value: ArtifactCreate): Promise<Artifact> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: Artifact = {
      id: `art-${Date.now()}`,
      artifact_type: "RESUME",
      title: value.title.trim(),
      external_url: value.external_url.trim(),
      created_at: now,
      updated_at: now,
    };
    state.artifacts = [created, ...state.artifacts];
    saveApiState(state);
    return created;
  },

  async updateArtifact(id: string, value: ArtifactUpdate): Promise<Artifact> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: Artifact | null = null;
    state.artifacts = state.artifacts.map((item) => {
      if (item.id !== id) return item;
      updated = {
        ...item,
        title: value.title !== undefined ? value.title : item.title,
        external_url:
          value.external_url !== undefined ? value.external_url : item.external_url,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.artifacts[0];
  },

  async deleteArtifact(id: string): Promise<void> {
    const state = loadApiState();
    state.artifacts = state.artifacts.filter((a) => a.id !== id);
    saveApiState(state);
  },

  async listResumes(): Promise<Resume[]> {
    return loadApiState().resumes;
  },

  async createResume(payload: ResumeCreate): Promise<Resume> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: Resume = {
      id: `resume-${Date.now()}`,
      title: payload.title.trim(),
      created_at: now,
    };
    state.resumes = [created, ...state.resumes];
    state.resumeVersions[created.id] = [];
    saveApiState(state);
    return created;
  },

  async updateResume(id: string, payload: ResumeUpdate): Promise<Resume> {
    const state = loadApiState();
    let updated: Resume | null = null;
    state.resumes = state.resumes.map((r) => {
      if (r.id !== id) return r;
      updated = {
        ...r,
        title: payload.title !== undefined ? payload.title : r.title,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.resumes[0];
  },

  async deleteResume(id: string): Promise<void> {
    const state = loadApiState();
    state.resumes = state.resumes.filter((r) => r.id !== id);
    delete state.resumeVersions[id];
    saveApiState(state);
  },

  async listResumeVersions(resumeId: string): Promise<ResumeVersion[]> {
    const state = loadApiState();
    return state.resumeVersions[resumeId] ?? [];
  },

  async uploadResumeVersion(resumeId: string, file: File): Promise<ResumeVersion> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const existing = state.resumeVersions[resumeId] ?? [];
    const nextVersionNumber =
      existing.reduce((max, v) => Math.max(max, v.version_number), 0) + 1;
    const versionId = `version-${Date.now()}`;
    const isDocx =
      file.name?.toLowerCase().endsWith(".docx") ||
      file.type.includes("wordprocessingml");

    const updatedExisting = existing.map((v) => ({
      ...v,
      is_primary_active: false,
    }));

    const created: ResumeVersion = {
      id: versionId,
      resume_id: resumeId,
      version_number: nextVersionNumber,
      file_format: isDocx ? "DOCX" : "PDF",
      file_size_bytes: file.size || 156000,
      file_hash_sha256:
        "f4c8996fb92427ae41e4649b934ca495991b7852b855e3b0c44298fc1c149afb",
      is_primary_active: true,
      parse_status: "PARSED_SUCCESS",
      created_at: now,
    };

    state.resumeVersions[resumeId] = [created, ...updatedExisting];
    const currentSkillNames = (state.skillsSelection.skill_ids ?? []).map(
      skillIdToName
    );
    state.resumeEvidence[versionId] = buildEvidenceForSkillNames(
      versionId,
      currentSkillNames.slice(0, 10)
    );
    state.resumeExtractedText[versionId] = {
      raw_extracted_text: `ALEX RIVERA — Uploaded Resume (${file.name || "Resume.pdf"})\nSkills: ${currentSkillNames.join(", ")}`,
    };
    saveApiState(state);
    return created;
  },

  async setResumePrimaryVersion(
    resumeId: string,
    payload: ResumePrimaryVersionUpdate
  ): Promise<ResumeVersion> {
    const state = loadApiState();
    const existing = state.resumeVersions[resumeId] ?? [];
    let selected: ResumeVersion | null = null;
    state.resumeVersions[resumeId] = existing.map((v) => {
      const active = v.id === payload.version_id;
      const next = { ...v, is_primary_active: active };
      if (active) selected = next;
      return next;
    });
    saveApiState(state);
    return selected ?? state.resumeVersions[resumeId]?.[0];
  },

  async deleteResumeVersion(id: string): Promise<void> {
    const state = loadApiState();
    for (const resumeId of Object.keys(state.resumeVersions)) {
      state.resumeVersions[resumeId] = (state.resumeVersions[resumeId] ?? []).filter(
        (v) => v.id !== id
      );
    }
    delete state.resumeEvidence[id];
    delete state.resumeExtractedText[id];
    saveApiState(state);
  },

  resumeVersionFileUrl(id: string): string {
    return `#demo-resume-version-${encodeURIComponent(id)}`;
  },

  async parseResumeVersion(id: string): Promise<ResumeVersion> {
    const state = loadApiState();
    for (const resumeId of Object.keys(state.resumeVersions)) {
      for (const v of state.resumeVersions[resumeId] ?? []) {
        if (v.id === id) {
          v.parse_status = "PARSED_SUCCESS";
          saveApiState(state);
          return v;
        }
      }
    }
    return state.resumeVersions["resume-v2"][0];
  },

  async listResumeEvidence(id: string): Promise<ResumeEvidence[]> {
    const state = loadApiState();
    return state.resumeEvidence[id] ?? state.resumeEvidence["version-v2"] ?? [];
  },

  async getResumeExtractedText(id: string): Promise<ResumeExtractedText> {
    const state = loadApiState();
    return (
      state.resumeExtractedText[id] ??
      state.resumeExtractedText["version-v2"]
    );
  },

  async getSkills(): Promise<SkillSelection> {
    return loadApiState().skillsSelection;
  },

  async replaceSkills(values: SkillSelection): Promise<SkillSelection> {
    const state = loadApiState();
    state.skillsSelection = {
      skill_ids: Array.from(new Set(values.skill_ids ?? [])),
      custom_values: Array.from(new Set(values.custom_values ?? [])),
    };
    saveApiState(state);
    return state.skillsSelection;
  },

  async listProjects(): Promise<Project[]> {
    return loadApiState().projects;
  },

  async createProject(values: ProjectCreate): Promise<Project> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: Project = {
      id: `proj-${Date.now()}`,
      title: values.title.trim(),
      description: values.description ?? "",
      technologies: values.technologies ?? { skill_ids: [], custom_values: [] },
      project_url: values.project_url ?? null,
      repository_url: values.repository_url ?? null,
      created_at: now,
      updated_at: now,
    };
    state.projects = [created, ...state.projects];
    saveApiState(state);
    return created;
  },

  async updateProject(id: string, values: ProjectUpdate): Promise<Project> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: Project | null = null;
    state.projects = state.projects.map((p) => {
      if (p.id !== id) return p;
      updated = {
        ...p,
        title: values.title !== undefined ? values.title : p.title,
        description:
          values.description !== undefined ? values.description : p.description,
        technologies:
          values.technologies !== undefined ? values.technologies : p.technologies,
        project_url:
          values.project_url !== undefined ? values.project_url : p.project_url,
        repository_url:
          values.repository_url !== undefined
            ? values.repository_url
            : p.repository_url,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.projects[0];
  },

  async deleteProject(id: string): Promise<void> {
    const state = loadApiState();
    state.projects = state.projects.filter((p) => p.id !== id);
    saveApiState(state);
  },

  async getProfile(): Promise<Profile | null> {
    return loadApiState().profile;
  },

  async updateProfile(payload: ProfileUpdate): Promise<Profile> {
    const state = loadApiState();
    state.profile = {
      ...state.profile,
      ...payload,
      legal_first_name:
        payload.legal_first_name ?? state.profile.legal_first_name,
      legal_last_name: payload.legal_last_name ?? state.profile.legal_last_name,
    };
    saveApiState(state);
    return state.profile;
  },

  async getCandidateProfile(): Promise<CandidateProfile> {
    const state = loadApiState();
    const sourcesBySkill = getAllCandidateSkillSources(state);

    const skills: CandidateProfile["skills"] = [];
    for (const [skillId, sources] of sourcesBySkill.entries()) {
      const cat = SKILL_ID_TO_ITEM.get(skillId);
      skills.push({
        skill_id: skillId,
        name: cat?.name ?? skillId,
        category: cat?.category ?? "Technical",
        sources,
      });
    }

    const customSkills: CandidateProfile["custom_skills"] = (
      state.skillsSelection.custom_values ?? []
    ).map((name, idx) => ({
      name,
      sources: [
        {
          source_type: "CONFIRMED_BY_USER",
          source_id: `custom-skill-${idx + 1}`,
        },
      ],
    }));

    const resumeEvidenceList: CandidateProfile["resume_evidence"] = [];
    for (const res of state.resumes) {
      const versions = state.resumeVersions[res.id] ?? [];
      for (const ver of versions) {
        if (!ver.is_primary_active) continue;
        for (const ev of state.resumeEvidence[ver.id] ?? []) {
          resumeEvidenceList.push({
            resume_id: res.id,
            resume_title: res.title,
            resume_version_id: ver.id,
            resume_version_number: ver.version_number,
            evidence_item_id: ev.id,
            ordinal: ev.ordinal,
            category: ev.category,
            section_header: ev.section_header ?? null,
            bullet_text: ev.bullet_text,
            recognized_skills: ev.recognized_skills ?? [],
          });
        }
      }
    }

    return {
      facts_source: "ADDED_BY_USER",
      profile: state.profile,
      education: state.education,
      employment: state.employment,
      work_authorizations: state.workAuthorizations,
      preferences: state.preferences,
      projects: state.projects,
      skills,
      custom_skills: customSkills,
      resume_evidence: resumeEvidenceList,
    };
  },

  async listJobs(params: JobSearchParams = {}): Promise<PublicJobSearch> {
    const state = loadApiState();
    const keyword = (params.keyword ?? params.query ?? "").trim().toLowerCase();
    const locQuery = (params.location ?? "").trim().toLowerCase();
    const companyQuery = (params.company ?? "").trim().toLowerCase();
    const reqQuery = (params.requirement ?? "").trim().toLowerCase();
    const empTypes = params.employment_type ?? params.type ?? params.job_type ?? [];
    const workModes = params.work_mode ?? [];
    const roles = params.role ?? [];
    const countries = params.country ?? [];
    const regions = params.region ?? [];
    const cities = params.city ?? [];
    const view = params.view ?? "all";

    const filtered = DEMO_JOBS.filter((spec) => {
      const isSaved = state.savedJobIds.includes(spec.id);
      const isHidden = state.hiddenJobIds.includes(spec.id);

      if (view === "saved" && !isSaved) return false;
      if (view === "hidden" && !isHidden) return false;
      if (view === "all" && isHidden) return false;

      if (keyword) {
        const haystack = [
          spec.title,
          spec.company_name,
          spec.description,
          ...spec.locations,
          ...spec.required_skills.map((s) => s.name),
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(keyword)) return false;
      }

      if (locQuery) {
        const locHaystack = spec.locations.join(" ").toLowerCase();
        if (!locHaystack.includes(locQuery)) return false;
      }

      if (companyQuery && !spec.company_name.toLowerCase().includes(companyQuery)) {
        return false;
      }

      if (
        reqQuery &&
        !spec.required_skills.some((s) => s.name.toLowerCase().includes(reqQuery))
      ) {
        return false;
      }

      if (empTypes.length > 0 && !empTypes.includes(spec.employment_type)) {
        return false;
      }

      if (workModes.length > 0 && !workModes.includes(spec.work_mode)) {
        return false;
      }

      if (
        roles.length > 0 &&
        !roles.some(
          (r) =>
            r === spec.role_id ||
            spec.role_name.toLowerCase().includes(r.toLowerCase())
        )
      ) {
        return false;
      }

      if (
        countries.length > 0 &&
        !countries.some((c) =>
          spec.locations.some((l) => l.toLowerCase().includes(c.toLowerCase()))
        )
      ) {
        return false;
      }

      if (
        regions.length > 0 &&
        !regions.some((r) =>
          spec.locations.some((l) => l.toLowerCase().includes(r.toLowerCase()))
        )
      ) {
        return false;
      }

      if (
        cities.length > 0 &&
        !cities.some((c) =>
          spec.locations.some((l) => l.toLowerCase().includes(c.toLowerCase()))
        )
      ) {
        return false;
      }

      return true;
    }).map((spec) =>
      toPublicJob(
        spec,
        state.savedJobIds.includes(spec.id),
        state.hiddenJobIds.includes(spec.id),
        state.viewedJobIds[spec.id] ?? null
      )
    );

    const page = params.page ?? 1;
    const pageSize = params.page_size ?? 20;

    return {
      items: filtered.slice((page - 1) * pageSize, page * pageSize),
      page,
      page_size: pageSize,
      total: filtered.length,
      total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)),
    };
  },

  async getJob(id: string): Promise<PublicJobDetail> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    return toPublicJobDetail(
      spec,
      state.savedJobIds.includes(spec.id),
      state.hiddenJobIds.includes(spec.id),
      state.viewedJobIds[spec.id] ?? null
    );
  },

  async updateJobState(
    id: string,
    payload: JobUserStateUpdate
  ): Promise<JobUserState> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    if (payload.saved !== undefined && payload.saved !== null) {
      if (payload.saved) {
        if (!state.savedJobIds.includes(spec.id)) {
          state.savedJobIds = [...state.savedJobIds, spec.id];
        }
      } else {
        state.savedJobIds = state.savedJobIds.filter((x) => x !== spec.id);
      }
    }
    if (payload.hidden !== undefined && payload.hidden !== null) {
      if (payload.hidden) {
        if (!state.hiddenJobIds.includes(spec.id)) {
          state.hiddenJobIds = [...state.hiddenJobIds, spec.id];
        }
      } else {
        state.hiddenJobIds = state.hiddenJobIds.filter((x) => x !== spec.id);
      }
    }
    if (payload.viewed) {
      state.viewedJobIds[spec.id] = new Date().toISOString();
    }
    saveApiState(state);
    const viewedAt = state.viewedJobIds[spec.id] ?? null;
    return {
      job_id: spec.id,
      saved: state.savedJobIds.includes(spec.id),
      hidden: state.hiddenJobIds.includes(spec.id),
      viewed_at: viewedAt,
      unseen: viewedAt === null,
    };
  },

  async listSavedSearches(): Promise<SavedJobSearch[]> {
    return loadApiState().savedSearches;
  },

  async createSavedSearch(payload: SavedJobSearchCreate): Promise<SavedJobSearch> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: SavedJobSearch = {
      id: `search-${Date.now()}`,
      name: payload.name.trim(),
      criteria: payload.criteria,
      alert_mode: payload.alert_mode ?? "INSTANT",
      alert_enabled_at: payload.alert_mode !== "OFF" ? now : null,
      created_at: now,
      updated_at: now,
    };
    state.savedSearches = [created, ...state.savedSearches];
    saveApiState(state);
    return created;
  },

  async updateSavedSearch(
    id: string,
    payload: SavedJobSearchUpdate
  ): Promise<SavedJobSearch> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: SavedJobSearch | null = null;
    state.savedSearches = state.savedSearches.map((s) => {
      if (s.id !== id) return s;
      const nextMode =
        payload.alert_mode !== undefined && payload.alert_mode !== null
          ? payload.alert_mode
          : s.alert_mode;
      updated = {
        ...s,
        name: payload.name !== undefined && payload.name !== null ? payload.name : s.name,
        criteria:
          payload.criteria !== undefined && payload.criteria !== null
            ? payload.criteria
            : s.criteria,
        alert_mode: nextMode,
        alert_enabled_at: nextMode === "OFF" ? null : s.alert_enabled_at ?? now,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.savedSearches[0];
  },

  async deleteSavedSearch(id: string): Promise<void> {
    const state = loadApiState();
    state.savedSearches = state.savedSearches.filter((s) => s.id !== id);
    saveApiState(state);
  },

  async listAlerts(): Promise<JobAlertInbox> {
    const state = loadApiState();
    return {
      items: state.alerts,
      unread_count: state.alerts.filter((a) => !a.read_at).length,
    };
  },

  async markAlertRead(id: string): Promise<JobAlertReadState> {
    const state = loadApiState();
    const now = new Date().toISOString();
    state.alerts = state.alerts.map((a) =>
      a.id === id ? { ...a, read_at: a.read_at ?? now } : a
    );
    saveApiState(state);
    return {
      id,
      read_at: now,
    };
  },

  async getJobFit(id: string): Promise<FitAnalysis> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    const sourcesBySkill = getAllCandidateSkillSources(state);

    const matched: FitAnalysis["matched"] = [];
    const missing: FitAnalysis["missing"] = [];

    for (const req of spec.required_skills) {
      const skillId = skillNameToId(req.name);
      const sources = sourcesBySkill.get(skillId) ?? [];
      if (sources.length > 0) {
        matched.push({
          category: "SKILL",
          requirement_id: skillId,
          name: req.name,
          importance: req.importance,
          description: req.description,
          explanation: `Recorded in ${sources.length} candidate evidence source(s) (${sources
            .map((s) =>
              s.source_type === "PROJECT"
                ? `Project: ${s.project_title}`
                : s.source_type === "RESUME_EVIDENCE"
                  ? `${s.resume_title} v${s.resume_version_number}`
                  : "Confirmed Skill"
            )
            .join(", ")}).`,
          limitation: "Exact catalog match; does not measure depth of experience.",
          sources,
        });
      } else {
        missing.push({
          category: "SKILL",
          requirement_id: skillId,
          name: req.name,
          importance: req.importance,
          description: req.description,
          explanation: `No recorded evidence for ${req.name} in your confirmed skills, projects, or parsed resume versions.`,
          limitation:
            "If you have coursework or project proof for this skill, add it to Skills or Projects.",
          sources: [],
        });
      }
    }

    return {
      job_id: spec.id,
      job_title: spec.title,
      company_name: spec.company_name,
      matched,
      missing,
      unknown: [],
      limitations: [
        "Fit analysis compares explicit posting requirements against your recorded Candidate Profile and parsed resume evidence.",
        "It never fabricates qualifications or computes arbitrary percentage scores.",
      ],
    };
  },

  async getJobResumeAlignment(
    id: string,
    resumeVersionId: string
  ): Promise<ResumeAlignment> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    const { resume, version, evidence } = resolveResumeVersion(
      state,
      resumeVersionId
    );
    const sourcesBySkill = getAllCandidateSkillSources(state);

    const resumeSkillIds = new Set<string>();
    for (const ev of evidence) {
      for (const rec of ev.recognized_skills ?? []) {
        resumeSkillIds.add(rec.skill_id);
      }
    }

    const shownOnResume: ResumeAlignment["shown_on_resume"] = [];
    const candidateEvidenceNotShown: ResumeAlignment["candidate_evidence_not_shown"] = [];
    const noRecordedEvidence: ResumeAlignment["no_recorded_evidence"] = [];

    for (const req of spec.required_skills) {
      const skillId = skillNameToId(req.name);
      const allSources = sourcesBySkill.get(skillId) ?? [];
      const versionSources = allSources.filter(
        (s) =>
          s.source_type === "RESUME_EVIDENCE" &&
          s.resume_version_id === version.id
      );

      if (resumeSkillIds.has(skillId)) {
        shownOnResume.push({
          category: "SKILL",
          requirement_id: skillId,
          name: req.name,
          importance: req.importance,
          description: req.description,
          explanation: `Explicitly recognized in ${resume.title} (Version ${version.version_number}).`,
          limitation: "Verified via deterministic resume parser evidence.",
          sources: versionSources.length > 0 ? versionSources : allSources,
        });
      } else if (allSources.length > 0) {
        candidateEvidenceNotShown.push({
          category: "SKILL",
          requirement_id: skillId,
          name: req.name,
          importance: req.importance,
          description: req.description,
          explanation: `Recorded in your Candidate Profile (${allSources
            .map((s) => s.project_title || "Confirmed Skills")
            .join(", ")}), but not detected on ${resume.title} (v${version.version_number}).`,
          limitation:
            "Consider surfacing this existing evidence on your resume before applying.",
          sources: allSources,
        });
      } else {
        noRecordedEvidence.push({
          category: "SKILL",
          requirement_id: skillId,
          name: req.name,
          importance: req.importance,
          description: req.description,
          explanation: `Not recorded in ${resume.title} or in your Candidate Profile.`,
          limitation: "Do not claim this skill on your resume without real evidence.",
          sources: [],
        });
      }
    }

    return {
      job_id: spec.id,
      job_title: spec.title,
      company_name: spec.company_name,
      resume_id: resume.id,
      resume_title: resume.title,
      resume_version_id: version.id,
      resume_version_number: version.version_number,
      shown_on_resume: shownOnResume,
      candidate_evidence_not_shown: candidateEvidenceNotShown,
      no_recorded_evidence: noRecordedEvidence,
      unknown_unassessed: [],
      limitations: [
        "Compares explicit job requirements against parser evidence for the selected resume version and your Candidate Profile.",
      ],
    };
  },

  async getJobSkillGaps(
    id: string,
    resumeVersionId: string
  ): Promise<SkillGapAnalysis> {
    const alignment = await this.getJobResumeAlignment(id, resumeVersionId);

    const covered: SkillGapAnalysis["covered"] = (
      alignment.shown_on_resume ?? []
    ).map((item) => ({
      ...item,
      classification: "COVERED",
    }));

    const presentationGaps: SkillGapAnalysis["resume_presentation_gaps"] = (
      alignment.candidate_evidence_not_shown ?? []
    ).map((item) => ({
      ...item,
      classification: "RESUME_PRESENTATION_GAP",
    }));

    const evidenceGaps: SkillGapAnalysis["candidate_evidence_gaps"] = (
      alignment.no_recorded_evidence ?? []
    ).map((item) => ({
      ...item,
      classification: "CANDIDATE_EVIDENCE_GAP",
    }));

    return {
      job_id: alignment.job_id,
      job_title: alignment.job_title,
      company_name: alignment.company_name,
      resume_id: alignment.resume_id,
      resume_title: alignment.resume_title,
      resume_version_id: alignment.resume_version_id,
      resume_version_number: alignment.resume_version_number,
      covered,
      resume_presentation_gaps: presentationGaps,
      candidate_evidence_gaps: evidenceGaps,
      unknown: [],
      limitations: [
        "Separates presentation gaps (skills you already have in your profile but omitted from this resume) from true evidence gaps.",
      ],
    };
  },

  async getResumeImprovementPlan(
    id: string,
    resumeVersionId: string
  ): Promise<ResumeImprovementPlan> {
    const alignment = await this.getJobResumeAlignment(id, resumeVersionId);

    const keep: ResumeImprovementPlan["keep"] = (
      alignment.shown_on_resume ?? []
    ).map((item) => ({
      category: item.category,
      action: "KEEP",
      requirement_id: item.requirement_id,
      name: item.name,
      importance: item.importance,
      description: item.description,
      reason: `${item.name} is already clearly evidenced on ${alignment.resume_title} (v${alignment.resume_version_number}). Keep these bullets prominent.`,
      limitation: item.limitation,
      sources: item.sources,
    }));

    const considerAdding: ResumeImprovementPlan["consider_adding_existing_evidence"] =
      (alignment.candidate_evidence_not_shown ?? []).map((item) => ({
        category: item.category,
        action: "CONSIDER_ADDING_EXISTING_EVIDENCE",
        requirement_id: item.requirement_id,
        name: item.name,
        importance: item.importance,
        description: item.description,
        reason: `You already have recorded evidence for ${item.name} in your profile/projects, but it does not appear on this resume version.`,
        limitation: item.limitation,
        sources: item.sources,
      }));

    const doNotClaim: ResumeImprovementPlan["do_not_claim_without_evidence"] = (
      alignment.no_recorded_evidence ?? []
    ).map((item) => ({
      category: item.category,
      action: "DO_NOT_CLAIM_WITHOUT_EVIDENCE",
      requirement_id: item.requirement_id,
      name: item.name,
      importance: item.importance,
      description: item.description,
      reason: `No recorded evidence for ${item.name} in your workspace. Record real coursework or project proof before adding to a resume.`,
      limitation: item.limitation,
      sources: [],
    }));

    return {
      job_id: alignment.job_id,
      job_title: alignment.job_title,
      company_name: alignment.company_name,
      resume_id: alignment.resume_id,
      resume_title: alignment.resume_title,
      resume_version_id: alignment.resume_version_id,
      resume_version_number: alignment.resume_version_number,
      keep,
      consider_adding_existing_evidence: considerAdding,
      do_not_claim_without_evidence: doNotClaim,
      manual_review: [],
      limitations: alignment.limitations,
    };
  },

  async getResumeTailoringDraft(
    id: string,
    resumeVersionId: string
  ): Promise<ResumeTailoringDraft> {
    const plan = await this.getResumeImprovementPlan(id, resumeVersionId);

    const keep: ResumeTailoringDraft["keep"] = (plan.keep ?? []).map((item) => ({
      ...item,
      draft_text: `Retain existing ${item.name} bullet on ${plan.resume_title}: "Engineered and verified ${item.name} components in Waterloo Systems Lab and technical projects with automated regression testing."`,
    }));

    const draftSuggestions: ResumeTailoringDraft["draft_suggestions"] = (
      plan.consider_adding_existing_evidence ?? []
    ).map((item) => ({
      ...item,
      draft_text: `Add grounded ${item.name} bullet from your profile: "Developed and tested ${item.name} workflows in undergraduate CS projects, verifying correctness with automated CI checks."`,
    }));

    const unsupported: ResumeTailoringDraft["unsupported"] = (
      plan.do_not_claim_without_evidence ?? []
    ).map((item) => ({
      ...item,
      draft_text: null,
    }));

    return {
      job_id: plan.job_id,
      job_title: plan.job_title,
      company_name: plan.company_name,
      resume_id: plan.resume_id,
      resume_title: plan.resume_title,
      resume_version_id: plan.resume_version_id,
      resume_version_number: plan.resume_version_number,
      keep,
      draft_suggestions: draftSuggestions,
      unsupported,
      manual_review: [],
      limitations: [
        "Every draft suggestion is strictly grounded in your recorded Candidate Profile and parsed resume evidence.",
      ],
    };
  },

  async getResumeTailoringReview(
    id: string,
    resumeVersionId: string
  ): Promise<ResumeTailoringReview> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    const { resume, version } = resolveResumeVersion(state, resumeVersionId);
    const key = `${spec.id}:${version.id}`;

    if (state.tailoringReviews[key]) {
      return state.tailoringReviews[key];
    }

    const draft = await this.getResumeTailoringDraft(spec.id, version.id);
    const now = new Date().toISOString();
    const reviewId = `rev-${spec.id}-${version.id}`;

    const allDraftItems = [
      ...(draft.keep ?? []),
      ...(draft.draft_suggestions ?? []),
    ];

    const items: NonNullable<ResumeTailoringReview["items"]> = allDraftItems.map(
      (d, idx) => ({
        id: `rev-item-${spec.id}-${idx + 1}`,
        ordinal: idx + 1,
        category: d.category,
        action: d.action,
        requirement_id: d.requirement_id,
        name: d.name,
        importance: d.importance ?? "REQUIRED",
        description: d.description ?? null,
        original_draft_text:
          d.draft_text ??
          `Highlight ${d.name} evidence from ${resume.title} for ${spec.company_name}.`,
        reason: d.reason,
        limitation: d.limitation,
        provenance: d.sources ?? [],
        decision: idx === 0 ? "ACCEPTED" : "PENDING",
        user_edited_text: null,
        created_at: now,
        updated_at: now,
      })
    );

    const review: ResumeTailoringReview = {
      id: reviewId,
      status: "DRAFT",
      job_id: spec.id,
      job_title: spec.title,
      company_name: spec.company_name,
      source_resume_version_id: version.id,
      resume_title: resume.title,
      resume_version_number: version.version_number,
      items,
      created_at: now,
      updated_at: now,
      finalized_at: null,
    };

    state.tailoringReviews[key] = review;
    saveApiState(state);
    return review;
  },

  async createResumeTailoringReview(
    id: string,
    payload: ResumeTailoringReviewCreate
  ): Promise<ResumeTailoringReview> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    const { version } = resolveResumeVersion(state, payload.resume_version_id);
    const key = `${spec.id}:${version.id}`;
    delete state.tailoringReviews[key];
    saveApiState(state);
    return this.getResumeTailoringReview(spec.id, version.id);
  },

  async updateResumeTailoringReviewItem(
    id: string,
    reviewId: string,
    itemId: string,
    payload: ResumeTailoringReviewItemUpdate
  ): Promise<ResumeTailoringReview> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    let targetKey = Object.keys(state.tailoringReviews).find(
      (k) => state.tailoringReviews[k]?.id === reviewId
    );
    if (!targetKey) {
      const initial = await this.getResumeTailoringReview(spec.id, "version-v2");
      targetKey = `${spec.id}:${initial.source_resume_version_id}`;
    }

    const review = state.tailoringReviews[targetKey];
    const now = new Date().toISOString();
    const existingItems = review.items ?? [];
    const updatedItems = existingItems.map((item) => {
      if (item.id !== itemId) return item;
      return {
        ...item,
        decision:
          payload.decision !== undefined && payload.decision !== null
            ? payload.decision
            : item.decision,
        user_edited_text:
          payload.user_edited_text !== undefined
            ? payload.user_edited_text
            : item.user_edited_text,
        updated_at: now,
      };
    });

    const updatedReview: ResumeTailoringReview = {
      ...review,
      items: updatedItems,
      updated_at: now,
    };

    state.tailoringReviews[targetKey] = updatedReview;
    saveApiState(state);
    return updatedReview;
  },

  async finalizeResumeTailoringReview(
    id: string,
    reviewId: string
  ): Promise<ResumeTailoringReview> {
    const state = loadApiState();
    const spec = findJobSpec(id);
    let targetKey = Object.keys(state.tailoringReviews).find(
      (k) => state.tailoringReviews[k]?.id === reviewId
    );
    if (!targetKey) {
      const initial = await this.getResumeTailoringReview(spec.id, "version-v2");
      targetKey = `${spec.id}:${initial.source_resume_version_id}`;
    }
    const review = state.tailoringReviews[targetKey];
    const now = new Date().toISOString();
    const finalized: ResumeTailoringReview = {
      ...review,
      status: "FINALIZED",
      items: (review.items ?? []).map((item) => ({
        ...item,
        decision: item.decision === "PENDING" ? "ACCEPTED" : item.decision,
        updated_at: now,
      })),
      updated_at: now,
      finalized_at: now,
    };
    state.tailoringReviews[targetKey] = finalized;
    saveApiState(state);
    return finalized;
  },

  async listEducation(): Promise<Education[]> {
    return loadApiState().education;
  },

  async createEducation(payload: EducationCreate): Promise<Education> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: Education = {
      id: `edu-${Date.now()}`,
      institution_name: payload.institution_name,
      degree_level: payload.degree_level,
      major: payload.major,
      minor: payload.minor ?? null,
      study_year: payload.study_year,
      start_date: payload.start_date,
      expected_grad_month: payload.expected_grad_month,
      expected_grad_year: payload.expected_grad_year,
      gpa_value:
        payload.gpa_value !== undefined && payload.gpa_value !== null
          ? String(payload.gpa_value)
          : null,
      gpa_scale:
        payload.gpa_scale !== undefined && payload.gpa_scale !== null
          ? String(payload.gpa_scale)
          : null,
      gpa_include_on_apps: Boolean(payload.gpa_include_on_apps),
      is_primary: Boolean(payload.is_primary),
      created_at: now,
      updated_at: now,
    };
    state.education = [created, ...state.education];
    saveApiState(state);
    return created;
  },

  async updateEducation(id: string, payload: EducationUpdate): Promise<Education> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: Education | null = null;
    state.education = state.education.map((ed) => {
      if (ed.id !== id) return ed;
      updated = {
        ...ed,
        institution_name:
          payload.institution_name !== undefined
            ? payload.institution_name
            : ed.institution_name,
        degree_level:
          payload.degree_level !== undefined
            ? payload.degree_level
            : ed.degree_level,
        major: payload.major !== undefined ? payload.major : ed.major,
        minor: payload.minor !== undefined ? payload.minor : ed.minor,
        study_year:
          payload.study_year !== undefined ? payload.study_year : ed.study_year,
        start_date:
          payload.start_date !== undefined ? payload.start_date : ed.start_date,
        expected_grad_month:
          payload.expected_grad_month !== undefined
            ? payload.expected_grad_month
            : ed.expected_grad_month,
        expected_grad_year:
          payload.expected_grad_year !== undefined
            ? payload.expected_grad_year
            : ed.expected_grad_year,
        gpa_value:
          payload.gpa_value !== undefined
            ? payload.gpa_value === null
              ? null
              : String(payload.gpa_value)
            : ed.gpa_value,
        gpa_scale:
          payload.gpa_scale !== undefined
            ? payload.gpa_scale === null
              ? null
              : String(payload.gpa_scale)
            : ed.gpa_scale,
        gpa_include_on_apps:
          payload.gpa_include_on_apps !== undefined
            ? payload.gpa_include_on_apps
            : ed.gpa_include_on_apps,
        is_primary:
          payload.is_primary !== undefined ? payload.is_primary : ed.is_primary,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.education[0];
  },

  async deleteEducation(id: string): Promise<void> {
    const state = loadApiState();
    state.education = state.education.filter((e) => e.id !== id);
    saveApiState(state);
  },

  async listEmployment(): Promise<Employment[]> {
    return loadApiState().employment;
  },

  async createEmployment(payload: EmploymentCreate): Promise<Employment> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: Employment = {
      id: `emp-${Date.now()}`,
      employer_name: payload.employer_name,
      job_title: payload.job_title,
      location: payload.location ?? null,
      start_date: payload.start_date,
      end_date: payload.end_date ?? null,
      currently_employed: Boolean(payload.currently_employed),
      description: payload.description ?? null,
      created_at: now,
      updated_at: now,
    };
    state.employment = [created, ...state.employment];
    saveApiState(state);
    return created;
  },

  async updateEmployment(
    id: string,
    payload: EmploymentUpdate
  ): Promise<Employment> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: Employment | null = null;
    state.employment = state.employment.map((emp) => {
      if (emp.id !== id) return emp;
      updated = {
        ...emp,
        employer_name:
          payload.employer_name !== undefined
            ? payload.employer_name
            : emp.employer_name,
        job_title:
          payload.job_title !== undefined ? payload.job_title : emp.job_title,
        location: payload.location !== undefined ? payload.location : emp.location,
        start_date:
          payload.start_date !== undefined ? payload.start_date : emp.start_date,
        end_date: payload.end_date !== undefined ? payload.end_date : emp.end_date,
        currently_employed:
          payload.currently_employed !== undefined
            ? payload.currently_employed
            : emp.currently_employed,
        description:
          payload.description !== undefined
            ? payload.description
            : emp.description,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.employment[0];
  },

  async deleteEmployment(id: string): Promise<void> {
    const state = loadApiState();
    state.employment = state.employment.filter((e) => e.id !== id);
    saveApiState(state);
  },

  async listWorkAuthorizations(): Promise<WorkAuthorization[]> {
    return loadApiState().workAuthorizations;
  },

  async createWorkAuthorization(
    payload: WorkAuthorizationCreate
  ): Promise<WorkAuthorization> {
    const state = loadApiState();
    const now = new Date().toISOString();
    const created: WorkAuthorization = {
      id: `wa-${Date.now()}`,
      country_code: payload.country_code.toUpperCase(),
      authorization_status: payload.authorization_status,
      requires_current_sponsorship: Boolean(payload.requires_current_sponsorship),
      requires_future_sponsorship: Boolean(payload.requires_future_sponsorship),
      notes: payload.notes ?? null,
      last_confirmed_at: now,
      created_at: now,
      updated_at: now,
    };
    state.workAuthorizations = [created, ...state.workAuthorizations];
    saveApiState(state);
    return created;
  },

  async updateWorkAuthorization(
    id: string,
    payload: WorkAuthorizationUpdate
  ): Promise<WorkAuthorization> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: WorkAuthorization | null = null;
    state.workAuthorizations = state.workAuthorizations.map((wa) => {
      if (wa.id !== id) return wa;
      updated = {
        ...wa,
        country_code:
          payload.country_code !== undefined
            ? payload.country_code.toUpperCase()
            : wa.country_code,
        authorization_status:
          payload.authorization_status !== undefined
            ? payload.authorization_status
            : wa.authorization_status,
        requires_current_sponsorship:
          payload.requires_current_sponsorship !== undefined
            ? payload.requires_current_sponsorship
            : wa.requires_current_sponsorship,
        requires_future_sponsorship:
          payload.requires_future_sponsorship !== undefined
            ? payload.requires_future_sponsorship
            : wa.requires_future_sponsorship,
        notes: payload.notes !== undefined ? payload.notes : wa.notes,
        last_confirmed_at: now,
        updated_at: now,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.workAuthorizations[0];
  },

  async deleteWorkAuthorization(id: string): Promise<void> {
    const state = loadApiState();
    state.workAuthorizations = state.workAuthorizations.filter((w) => w.id !== id);
    saveApiState(state);
  },

  async getPreferences(): Promise<Preferences> {
    return loadApiState().preferences;
  },

  async replacePreferences(payload: Preferences): Promise<Preferences> {
    const state = loadApiState();
    state.preferences = { ...state.preferences, ...payload };
    saveApiState(state);
    return state.preferences;
  },

  async listRoles(): Promise<CatalogItem[]> {
    return ROLES_CATALOG;
  },

  async listSkills(): Promise<CatalogItem[]> {
    return SKILLS_CATALOG;
  },

  async listCompanies(): Promise<CatalogItem[]> {
    return COMPANIES_CATALOG;
  },

  async listLocations(): Promise<CatalogLocation[]> {
    return LOCATIONS_CATALOG;
  },

  async listIndustries(): Promise<CatalogItem[]> {
    return INDUSTRIES_CATALOG;
  },

  async listApplications(status?: ApplicationFilterStatus): Promise<Application[]> {
    const state = loadApiState();
    if (!status || status === "ALL") {
      return state.applications;
    }
    return state.applications.filter((a) => a.current_status === status);
  },

  async createApplication(payload: ApplicationCreate): Promise<Application> {
    const state = loadApiState();
    const spec = findJobSpec(payload.canonical_job_id);
    const existing = state.applications.find(
      (a) => a.canonical_job_id === spec.id
    );
    if (existing) {
      return existing;
    }
    const { resume, version } = resolveResumeVersion(
      state,
      payload.resume_version_id
    );
    const now = new Date().toISOString();
    const created: Application = {
      id: `app-${spec.id}-${Date.now()}`,
      canonical_job_id: spec.id,
      job_title: spec.title,
      company_name: spec.company_name,
      application_url: spec.application_url,
      job_lifecycle: "ACTIVE",
      current_status: "APPLIED",
      resume_version_id: version.id,
      resume_title: resume.title,
      resume_version_number: version.version_number,
      applied_at: payload.applied_at ?? now,
      notes:
        payload.notes ??
        `Tracked ${spec.company_name} (${spec.title}) with ${resume.title}.`,
      version: 1,
      created_at: now,
      updated_at: now,
      history: [
        {
          id: `hist-${Date.now()}`,
          previous_status: null,
          new_status: "APPLIED",
          notes: payload.notes ?? "Added to application tracker.",
          transitioned_at: now,
        },
      ],
    };
    state.applications = [created, ...state.applications];
    saveApiState(state);
    return created;
  },

  async getApplication(id: string): Promise<Application> {
    const state = loadApiState();
    return (
      state.applications.find((a) => a.id === id) ?? state.applications[0]
    );
  },

  async updateApplication(
    id: string,
    payload: ApplicationUpdate
  ): Promise<Application> {
    const state = loadApiState();
    const now = new Date().toISOString();
    let updated: Application | null = null;
    state.applications = state.applications.map((app) => {
      if (app.id !== id) return app;
      const nextStatus =
        payload.status !== undefined && payload.status !== null
          ? payload.status
          : app.current_status;
      const nextHistory = [...(app.history ?? [])];
      if (nextStatus !== app.current_status) {
        nextHistory.push({
          id: `hist-${Date.now()}`,
          previous_status: app.current_status,
          new_status: nextStatus,
          notes: payload.status_note ?? `Updated status to ${nextStatus}.`,
          transitioned_at: now,
        });
      }
      updated = {
        ...app,
        current_status: nextStatus,
        notes: payload.notes !== undefined ? payload.notes : app.notes,
        version: app.version + 1,
        updated_at: now,
        history: nextHistory,
      };
      return updated;
    });
    saveApiState(state);
    return updated ?? state.applications[0];
  },

  async getHealthLive(): Promise<HealthLiveResponse> {
    return {
      status: "ok",
      timestamp: new Date().toISOString(),
    };
  },

  async getHealthReady(): Promise<HealthReadyResponse> {
    return {
      status: "ready",
      dependencies: {
        database: true,
        storage: true,
      },
      timestamp: new Date().toISOString(),
    };
  },
};
