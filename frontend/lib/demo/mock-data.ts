/**
 * Internally consistent, fictional university student dataset for StudentSuccessful Demo Mode.
 *
 * All records—profile qualifications, technical skills, projects, resume versions,
 * illustrative 2027 internship snapshots, and tracked applications—are linked so changes
 * in one view immediately reflect in Fit Analysis, Resume Alignment, and the Tracker.
 */

export type ApplicationStage = "Saved" | "Applied" | "Interview" | "Offer" | "Rejected";

export interface InternshipJob {
  id: string;
  numericId: number;
  brand: "amd" | "nvidia" | "amazon" | "ibm";
  company: string;
  title: string;
  city: string;
  country: string;
  mode: string;
  term: string;
  reqId: string;
  requirements: string[];
  short: string;
  url: string;
}

export interface ProjectEvidence {
  id: string;
  title: string;
  role: string;
  timeframe: string;
  skills: string[];
  summary: string;
  impact: string;
}

export interface ResumeVersionRecord {
  id: "v1" | "v2";
  numericResumeId: number;
  label: string;
  filename: string;
  updatedAt: string;
  targetFocus: string;
  includedSkills: string[];
  highlights: string[];
}

export interface TrackedApplication {
  id: string;
  jobId?: string;
  role: string;
  company: string;
  brand?: "amd" | "nvidia" | "amazon" | "ibm";
  location: string;
  stage: ApplicationStage;
  date: string;
  resumeVersion: "v1" | "v2";
  notes: string;
  url?: string;
}

export interface DemoLandingProfile {
  id: string;
  fullName: string;
  preferredName: string;
  email: string;
  university: string;
  program: string;
  academicYear: string;
  graduationYear: number;
  gpa: string;
  location: string;
  workAuthorization: string;
  preferredTerms: string[];
  preferredLocations: string[];
  preferredModes: string[];
  bio: string;
  skills: string[];
  projects: ProjectEvidence[];
  onboarding_completed_at: string;
}

export interface DemoWorkspaceState {
  profile: DemoLandingProfile;
  resumes: ResumeVersionRecord[];
  activeResumeId: "v1" | "v2";
  savedJobIds: string[];
  selectedJobId: string;
  applications: TrackedApplication[];
}

export const OFFICIAL_2027_JOBS: InternshipJob[] = [
  {
    id: "amd-sw",
    numericId: 1001,
    brand: "amd",
    company: "AMD",
    title: "Short Term 2027 Software Engineering Intern/Co-Op",
    city: "Markham",
    country: "Canada",
    mode: "On-site",
    term: "2027 · 4–8 months",
    reqId: "91368",
    requirements: ["C/C++", "Python", "Linux", "PostgreSQL", "Git"],
    short:
      "Work alongside AMD software engineers on applications, automation scripts, software testing, and systems debugging.",
    url: "https://careers.amd.com/students/jobs/91368?lang=en-us",
  },
  {
    id: "nvidia-sw",
    numericId: 1002,
    brand: "nvidia",
    company: "NVIDIA",
    title: "2027 Internships: Software Engineering",
    city: "Santa Clara",
    country: "United States",
    mode: "Not specified",
    term: "2027 · 12 weeks",
    reqId: "JR2023495",
    requirements: ["Python", "C++", "React", "SQL", "Docker"],
    short:
      "Build developer tools, cloud platform infrastructure, and core software engineering projects across NVIDIA teams.",
    url: "https://jobs.nvidia.com/careers/job/893397026205",
  },
  {
    id: "amazon-sde",
    numericId: 1003,
    brand: "amazon",
    company: "Amazon",
    title: "Software Development Engineer Intern — Summer 2027",
    city: "Vancouver",
    country: "Canada",
    mode: "On-site",
    term: "Summer 2027 · 12 weeks",
    reqId: "10553947",
    requirements: ["Python", "Java", "Data Structures", "AWS", "SQL"],
    short:
      "Design, test, and operate distributed software services and customer-facing products with Amazon engineering teams.",
    url: "https://amazon.jobs/en/jobs/10553947/software-development-engineer-intern-summer-2027-can",
  },
  {
    id: "ibm-dev",
    numericId: 1004,
    brand: "ibm",
    company: "IBM",
    title: "Software Developer Intern 2027",
    city: "Markham",
    country: "Canada",
    mode: "Not specified",
    term: "2027 · Internship",
    reqId: "129661",
    requirements: ["Software Development", "Programming", "Testing"],
    short:
      "Contribute to enterprise software development, automated verification, and cloud services at IBM Software in Markham.",
    url: "https://careers.ibm.com/en_US/careers/JobDetail/Software-Developer-Intern-2027/129661",
  },
  {
    id: "amd-graphics",
    numericId: 1005,
    brand: "amd",
    company: "AMD",
    title: "Short Term 2027 Graphics Software Engineering Intern/Co-Op",
    city: "Markham",
    country: "Canada",
    mode: "On-site",
    term: "2027 · 4–8 months",
    reqId: "91359",
    requirements: ["C++", "Graphics", "Linux", "Debugging"],
    short:
      "Contribute to graphics driver development, rendering pipelines, and low-level systems debugging with AMD engineering.",
    url: "https://careers.amd.com/careers-home/jobs/91359?icims=1",
  },
  {
    id: "amazon-ml",
    numericId: 1006,
    brand: "amazon",
    company: "Amazon",
    title: "ML Systems Software Development Engineer Intern — 2027",
    city: "Toronto",
    country: "Canada",
    mode: "Not specified",
    term: "2027 · Internship",
    reqId: "10538066",
    requirements: ["Python", "C++", "Machine Learning", "React", "TypeScript"],
    short:
      "Work on machine learning infrastructure, developer observability tools, and high-throughput systems at Annapurna Labs.",
    url: "https://www.amazon.jobs/en/jobs/10538066/ml-systems-software-development-engineer-intern-annapurna-labs-2027",
  },
];

export const ALL_KNOWN_SKILLS: string[] = [
  "Python",
  "C/C++",
  "C++",
  "React",
  "TypeScript",
  "PostgreSQL",
  "SQL",
  "Linux",
  "Git",
  "Docker",
  "Java",
  "Data Structures",
  "AWS",
  "Software Development",
  "Programming",
  "Testing",
  "Graphics",
  "Debugging",
  "Machine Learning",
];

export function createInitialDemoState(): DemoWorkspaceState {
  return {
    profile: {
      id: "demo-student-alex-2027",
      fullName: "Alex Rivera",
      preferredName: "Alex",
      email: "alex.rivera@university.edu",
      university: "University of Waterloo",
      program: "B.Sc. Honours Computer Science (Co-Op)",
      academicYear: "2B · Sophomore / 2nd Year",
      graduationYear: 2027,
      gpa: "3.85 / 4.00",
      location: "Waterloo, ON, Canada",
      workAuthorization: "Authorized for Canada Co-Op · Eligible for US J-1 Intern Visa sponsorship",
      preferredTerms: ["Summer 2027 (12–16 weeks)", "Spring/Fall 2027 Co-Op (4–8 months)"],
      preferredLocations: ["Markham, ON", "Toronto, ON", "Vancouver, BC", "Santa Clara, CA"],
      preferredModes: ["On-site", "Hybrid", "Remote"],
      bio: "Second-year Computer Science co-op student focused on systems programming, backend data pipelines, and clean React/TypeScript developer tooling.",
      skills: [
        "Python",
        "C/C++",
        "React",
        "TypeScript",
        "PostgreSQL",
        "SQL",
        "Linux",
        "Git",
        "Data Structures",
        "Testing",
        "Debugging",
      ],
      projects: [
        {
          id: "proj-1",
          title: "TraceFlow — Linux Systems & PostgreSQL Telemetry Agent",
          role: "Lead Student Developer · Systems Lab",
          timeframe: "May 2026 – Aug 2026",
          skills: ["C/C++", "Python", "Linux", "PostgreSQL", "Git", "Debugging"],
          summary:
            "Built a lightweight Linux daemon in C++ with Python CLI tooling that collects process metrics and indexes time-series logs into PostgreSQL.",
          impact:
            "Built indexed batch writes and regression checks for repeatable telemetry queries.",
        },
        {
          id: "proj-2",
          title: "CoOpMap — Full-Stack Course & Requirement Visualizer",
          role: "Creator & Full-Stack Engineer",
          timeframe: "Jan 2026 – Apr 2026",
          skills: ["React", "TypeScript", "Python", "SQL", "PostgreSQL", "Testing", "Software Development"],
          summary:
            "Designed an interactive prerequisite and skill-mapping web application for undergraduate CS students with automated unit and integration tests.",
          impact:
            "Implemented course planning features with automated tests for key interactions.",
        },
        {
          id: "proj-3",
          title: "Undergraduate Teaching Assistant — Data Structures & Algorithms",
          role: "Department of Computer Science",
          timeframe: "Sep 2026 – Present",
          skills: ["Data Structures", "C++", "Python", "Programming", "Debugging", "Testing"],
          summary:
            "Led weekly lab sections for first-year students covering memory management, graph algorithms, complexity analysis, and gdb debugging.",
          impact:
            "Authored automated grading harnesses in Python and C++ to give students clearer edge-case feedback.",
        },
      ],
      onboarding_completed_at: "2026-10-01T14:30:00.000Z",
    },
    resumes: [
      {
        id: "v2",
        numericResumeId: 102,
        label: "Resume v2 — Systems & Full-Stack Co-Op",
        filename: "Alex_Rivera_Systems_FullStack_2027_v2.pdf",
        updatedAt: "Oct 21, 2026",
        targetFocus: "Systems Engineering, C/C++, Linux & Backend Co-Op Roles (AMD, NVIDIA)",
        includedSkills: [
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
        ],
        highlights: [
          "Emphasizes C/C++ Linux telemetry daemon, gdb debugging, and PostgreSQL schema optimization.",
          "Includes Python test automation scripts and Git CI workflows.",
          "Tailored for 4–8 month co-op and systems-heavy software engineering internships.",
        ],
      },
      {
        id: "v1",
        numericResumeId: 101,
        label: "Resume v1 — General Software Engineering",
        filename: "Alex_Rivera_General_SWE_2027_v1.pdf",
        updatedAt: "Oct 12, 2026",
        targetFocus: "Web, Product & General SDE Internships (Amazon, IBM)",
        includedSkills: [
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
        ],
        highlights: [
          "Focuses on React/TypeScript web application architecture and REST APIs.",
          "Highlights Data Structures TA experience and unit testing coverage.",
          "Omits low-level C/C++ and Linux kernel bullet points to save space.",
        ],
      },
    ],
    activeResumeId: "v2",
    savedJobIds: ["amd-sw", "nvidia-sw", "amazon-ml"],
    selectedJobId: "amd-sw",
    applications: [
      {
        id: "app-amd-sw",
        jobId: "amd-sw",
        role: "Short Term 2027 Software Engineering Intern/Co-Op",
        company: "AMD",
        brand: "amd",
        location: "Markham, ON",
        stage: "Applied",
        date: "Oct 18, 2026",
        resumeVersion: "v2",
        notes:
          "Applied via official AMD Student Careers portal (Req #91368) using Resume v2. Matched all 5 core requirements (C/C++, Python, Linux, PostgreSQL, Git).",
        url: "https://careers.amd.com/students/jobs/91368?lang=en-us",
      },
      {
        id: "app-nvidia-sw",
        jobId: "nvidia-sw",
        role: "2027 Internships: Software Engineering",
        company: "NVIDIA",
        brand: "nvidia",
        location: "Santa Clara, CA",
        stage: "Interview",
        date: "Oct 15, 2026",
        resumeVersion: "v2",
        notes:
          "First-round technical screen scheduled. Preparing C++ systems design examples and reviewing Docker containerization.",
        url: "https://jobs.nvidia.com/careers/job/893397026205",
      },
      {
        id: "app-amazon-sde",
        jobId: "amazon-sde",
        role: "Software Development Engineer Intern — Summer 2027",
        company: "Amazon",
        brand: "amazon",
        location: "Vancouver, BC",
        stage: "Applied",
        date: "Oct 11, 2026",
        resumeVersion: "v1",
        notes:
          "Completed online coding assessment. Need to add AWS cloud deployment evidence to Resume v1 before final loop.",
        url: "https://amazon.jobs/en/jobs/10553947/software-development-engineer-intern-summer-2027-can",
      },
      {
        id: "app-ibm-dev",
        jobId: "ibm-dev",
        role: "Software Developer Intern 2027",
        company: "IBM",
        brand: "ibm",
        location: "Markham, ON",
        stage: "Offer",
        date: "Oct 04, 2026",
        resumeVersion: "v1",
        notes:
          "Received internship offer from IBM Software Markham (Req #129661)! Reviewing start-date details with university co-op coordinator.",
        url: "https://careers.ibm.com/en_US/careers/JobDetail/Software-Developer-Intern-2027/129661",
      },
    ],
  };
}
