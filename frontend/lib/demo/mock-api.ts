import {
  ApplicationStage,
  DemoLandingProfile,
  DemoWorkspaceState,
  InternshipJob,
  OFFICIAL_2027_JOBS,
  ProjectEvidence,
  TrackedApplication,
} from "./mock-data";
import { loadDemoState, resetDemoState, saveDemoState } from "./demo-storage";

/**
 * Mock API service layer that powers the interactive landing page previews
 * and syncs with the full Next.js workspace demo state in localStorage.
 */
export const mockApi = {
  getWorkspace(): DemoWorkspaceState {
    return loadDemoState();
  },

  getJobs(): InternshipJob[] {
    return OFFICIAL_2027_JOBS;
  },

  selectJob(jobId: string): DemoWorkspaceState {
    const state = loadDemoState();
    const next: DemoWorkspaceState = { ...state, selectedJobId: jobId };
    saveDemoState(next);
    return next;
  },

  toggleSaveJob(jobId: string): DemoWorkspaceState {
    const state = loadDemoState();
    const exists = state.savedJobIds.includes(jobId);
    const savedJobIds = exists
      ? state.savedJobIds.filter((id) => id !== jobId)
      : [...state.savedJobIds, jobId];
    const next: DemoWorkspaceState = { ...state, savedJobIds };
    saveDemoState(next);
    return next;
  },

  updateProfile(patch: Partial<DemoLandingProfile>): DemoWorkspaceState {
    const state = loadDemoState();
    const next: DemoWorkspaceState = {
      ...state,
      profile: {
        ...state.profile,
        ...patch,
      },
    };
    saveDemoState(next);
    return next;
  },

  toggleProfileSkill(skill: string): DemoWorkspaceState {
    const state = loadDemoState();
    const hasSkill = state.profile.skills.includes(skill);
    const skills = hasSkill
      ? state.profile.skills.filter((s) => s !== skill)
      : [...state.profile.skills, skill];
    const next: DemoWorkspaceState = {
      ...state,
      profile: {
        ...state.profile,
        skills,
      },
    };
    saveDemoState(next);
    return next;
  },

  addCustomSkill(skill: string): DemoWorkspaceState {
    const trimmed = skill.trim();
    const state = loadDemoState();
    if (!trimmed || state.profile.skills.includes(trimmed)) return state;
    const next: DemoWorkspaceState = {
      ...state,
      profile: {
        ...state.profile,
        skills: [...state.profile.skills, trimmed],
      },
    };
    saveDemoState(next);
    return next;
  },

  addProjectEvidence(project: Omit<ProjectEvidence, "id">): DemoWorkspaceState {
    const state = loadDemoState();
    const newProject: ProjectEvidence = {
      ...project,
      id: `proj-${Date.now()}`,
    };
    const mergedSkills = Array.from(
      new Set([...state.profile.skills, ...project.skills])
    );
    const next: DemoWorkspaceState = {
      ...state,
      profile: {
        ...state.profile,
        skills: mergedSkills,
        projects: [newProject, ...state.profile.projects],
      },
    };
    saveDemoState(next);
    return next;
  },

  setActiveResume(version: "v1" | "v2"): DemoWorkspaceState {
    const state = loadDemoState();
    const next: DemoWorkspaceState = { ...state, activeResumeId: version };
    saveDemoState(next);
    return next;
  },

  toggleResumeSkill(version: "v1" | "v2", skill: string): DemoWorkspaceState {
    const state = loadDemoState();
    const resumes = state.resumes.map((res) => {
      if (res.id !== version) return res;
      const has = res.includedSkills.includes(skill);
      return {
        ...res,
        updatedAt: "Just now",
        includedSkills: has
          ? res.includedSkills.filter((s) => s !== skill)
          : [...res.includedSkills, skill],
      };
    });
    const next: DemoWorkspaceState = { ...state, resumes };
    saveDemoState(next);
    return next;
  },

  addJobToTracker(
    job: InternshipJob,
    stage: ApplicationStage = "Applied"
  ): DemoWorkspaceState {
    const state = loadDemoState();
    const existing = state.applications.find(
      (app) =>
        app.jobId === job.id ||
        (app.company === job.company && app.role === job.title)
    );
    if (existing) {
      const applications = state.applications.map((app) =>
        app.id === existing.id ? { ...app, stage } : app
      );
      const next: DemoWorkspaceState = { ...state, applications };
      saveDemoState(next);
      return next;
    }

    const newApp: TrackedApplication = {
      id: `app-${job.id}-${Date.now()}`,
      jobId: job.id,
      role: job.title,
      company: job.company,
      brand: job.brand,
      location: `${job.city}, ${job.country === "Canada" ? "ON/BC" : "CA"}`,
      stage,
      date: "Oct 23, 2026",
      resumeVersion: state.activeResumeId,
      notes: `Added from Job Discovery (Ref #${job.reqId}). Preparing ${state.activeResumeId.toUpperCase()} alignment.`,
      url: job.url,
    };

    const next: DemoWorkspaceState = {
      ...state,
      applications: [newApp, ...state.applications],
    };
    saveDemoState(next);
    return next;
  },

  addCustomApplication(payload: {
    role: string;
    company: string;
    location: string;
    stage: ApplicationStage;
    resumeVersion: "v1" | "v2";
    notes: string;
  }): DemoWorkspaceState {
    const state = loadDemoState();
    const newApp: TrackedApplication = {
      id: `app-custom-${Date.now()}`,
      role: payload.role.trim(),
      company: payload.company.trim(),
      location: payload.location.trim() || "Remote / Hybrid",
      stage: payload.stage,
      date: "Oct 23, 2026",
      resumeVersion: payload.resumeVersion,
      notes: payload.notes.trim() || "Added to application tracker.",
    };
    const next: DemoWorkspaceState = {
      ...state,
      applications: [newApp, ...state.applications],
    };
    saveDemoState(next);
    return next;
  },

  updateApplicationStage(
    appId: string,
    stage: ApplicationStage
  ): DemoWorkspaceState {
    const state = loadDemoState();
    const applications = state.applications.map((app) =>
      app.id === appId ? { ...app, stage } : app
    );
    const next: DemoWorkspaceState = { ...state, applications };
    saveDemoState(next);
    return next;
  },

  updateApplicationNotes(appId: string, notes: string): DemoWorkspaceState {
    const state = loadDemoState();
    const applications = state.applications.map((app) =>
      app.id === appId ? { ...app, notes } : app
    );
    const next: DemoWorkspaceState = { ...state, applications };
    saveDemoState(next);
    return next;
  },

  deleteApplication(appId: string): DemoWorkspaceState {
    const state = loadDemoState();
    const applications = state.applications.filter((app) => app.id !== appId);
    const next: DemoWorkspaceState = { ...state, applications };
    saveDemoState(next);
    return next;
  },

  resetDemo(): DemoWorkspaceState {
    return resetDemoState();
  },
};
