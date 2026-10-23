"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import Image from "next/image";
import { OfferIntro } from "./OfferIntro";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  ArrowDownRight,
  Bookmark,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  Clock3,
  MailOpen,
  Database,
  FileCheck2,
  FilePenLine,
  FileSearch,
  Layers3,
  MapPin,
  Menu,
  PanelTop,
  Play,
  Search,
  ShieldCheck,
  Target,
  X,
} from "lucide-react";
import {
  ApplicationStage,
  InternshipJob,
  OFFICIAL_2027_JOBS,
} from "../../lib/demo/mock-data";
import { mockApi } from "../../lib/demo/mock-api";
import { isDemoModeEnabled } from "../../lib/demo/config";
import { activateDemoSession } from "../../lib/demo/demo-store";
import { useAuth } from "../auth/AuthProvider";

const BrandLogo = ({ brand, company }: { brand: string; company: string }) => (
  <span className={`ssi-company-logo ssi-logo-${brand}`}>
    <Image
      alt={`${company} logo`}
      src={`/brand-icons/${brand}.svg`}
      width={50}
      height={34}
    />
  </span>
);

const stages = ["Applied", "Interview", "Offer"] as const;
type Stage = (typeof stages)[number];

function Reveal({
  children,
  className = "",
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <div className={`ssi-reveal ${className}`} id={id}>
      {children}
    </div>
  );
}

const sectionTips: Record<string, string> = {
  discover:
    "Select any company role to inspect its requirements. Clicking Apply opens the official employer posting.",
  match:
    "Select skills to see which job requirements your profile covers.",
  resume:
    "Switch between Resume v1 and v2 to see which requirements are explicitly shown on each document.",
  track:
    "Update an application stage here — or open the full Interactive Demo to manage your entire pipeline.",
};

function CareerGuide({ section }: { section: string }) {
  const follower = useRef<HTMLDivElement>(null);
  const hoverKey = useRef("");
  const timeout = useRef<number | undefined>(undefined);
  const [enabled, setEnabled] = useState(true);
  const [speaking, setSpeaking] = useState(true);
  const [tip, setTip] = useState(
    "Hi, I'm Pip! Scroll through the workflow or launch the full Interactive Demo anytime."
  );
  const [waving, setWaving] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const el = follower.current;
    if (!el) return;
    const fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || reduced) return;
    let x = window.innerWidth - 95;
    let y = window.innerHeight - 130;
    let aimX = x,
      aimY = y,
      frame = 0;
    let active = true;
    el.style.transform = `translate3d(${x}px,${y}px,0)`;
    // Schedule frames only while Pip is travelling. An idle pointer uses no animation loop.
    const draw = () => {
      if (!active) return;
      x += (aimX - x) * 0.16;
      y += (aimY - y) * 0.16;
      el.style.transform = `translate3d(${x}px,${y}px,0)`;
      if (Math.abs(aimX - x) + Math.abs(aimY - y) > 0.8) {
        frame = window.requestAnimationFrame(draw);
      } else {
        x = aimX;
        y = aimY;
        el.style.transform = `translate3d(${x}px,${y}px,0)`;
        frame = 0;
      }
    };
    const move = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
      aimX = Math.min(window.innerWidth - 65, Math.max(8, e.clientX + 24));
      aimY = Math.min(window.innerHeight - 75, Math.max(12, e.clientY + 22));
      if (frame === 0) frame = window.requestAnimationFrame(draw);
      el.style.setProperty(
        "--ssi-pip-look-x",
        `${(e.clientX / window.innerWidth - 0.5) * 3}px`
      );
      el.style.setProperty(
        "--ssi-pip-look-y",
        `${(e.clientY / window.innerHeight - 0.5) * 2}px`
      );
    };
    window.addEventListener("pointermove", move, { passive: true });
    return () => {
      active = false;
      window.cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", move);
    };
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;
    hoverKey.current = "";
    setTip(
      sectionTips[section] ??
        "Hi, I'm Pip! Follow along — I'll show you how each career workflow connects."
    );
    setSpeaking(true);
    if (timeout.current) window.clearTimeout(timeout.current);
    timeout.current = window.setTimeout(() => setSpeaking(false), 7500);
    return () => {
      if (timeout.current) window.clearTimeout(timeout.current);
    };
  }, [section, enabled]);

  useEffect(() => {
    if (!enabled) return;
    const hints: [string, string][] = [
      [".ssi-try-demo-cta", "Open the full workspace to manage jobs, resumes, and applications."],
      [".ssi-external-apply", "Opens the official employer careers page in a new tab."],
      [".ssi-mark-applied", "Adds the role to the tracker below, without submitting an application."],
      [".ssi-save", "Bookmark an internship to keep it on your shortlist."],
      [".ssi-job-main", "Select an internship to inspect its required skills and role summary."],
      [".ssi-searchbar", "Filter postings by company name, role title, or skill."],
      [".ssi-skill-toggle", "Toggle a skill to see how your recorded evidence compares to the job."],
      [".ssi-version-switch", "Compare Resume v1 and v2 to spot skills missing from a specific file."],
      [".ssi-app-row select", "Update an application status and watch your pipeline summary adjust."],
      [".ssi-track-filters", "Filter tracked applications by stage."],
    ];
    const hint = (evt: Event) => {
      const target = evt.target;
      if (!(target instanceof Element)) return;
      const matching = hints.find(([selector]) => target.closest(selector));
      const key = matching?.[0] ?? "";
      if (!key || key === hoverKey.current) return;
      hoverKey.current = key;
      setTip(matching![1]);
      setWaving(true);
      setSpeaking(true);
      if (timeout.current) window.clearTimeout(timeout.current);
      timeout.current = window.setTimeout(() => {
        setSpeaking(false);
        setWaving(false);
      }, 4800);
    };
    document.addEventListener("pointerover", hint);
    document.addEventListener("focusin", hint);
    return () => {
      document.removeEventListener("pointerover", hint);
      document.removeEventListener("focusin", hint);
      if (timeout.current) window.clearTimeout(timeout.current);
    };
  }, [enabled]);

  const face = (
    <span className="ssi-pip-character" aria-hidden="true">
      <span className="ssi-pip-ear ssi-pip-ear-left" />
      <span className="ssi-pip-ear ssi-pip-ear-right" />
      <span className="ssi-pip-eyes">
        <i />
        <i />
      </span>
      <span className="ssi-pip-cheek ssi-pip-cheek-left" />
      <span className="ssi-pip-cheek ssi-pip-cheek-right" />
      <span className="ssi-pip-smile" />
      <span className="ssi-pip-arm ssi-pip-arm-left" />
      <span className={`ssi-pip-arm ssi-pip-arm-right${waving ? " is-waving" : ""}`} />
      <span className="ssi-pip-spark">✦</span>
    </span>
  );

  return (
    <>
      {enabled && (
        <div ref={follower} className="ssi-pip-follower" aria-hidden="true">
          {face}
        </div>
      )}
      {enabled && speaking && (
        <div className="ssi-pip-tip" role="status" aria-live="polite">
          <span className="ssi-pip-tip-star" aria-hidden="true">
            <i />
            <i />
          </span>
          <div>
            <strong>Pip · Your career buddy</strong>
            <p>{tip}</p>
          </div>
          <button
            type="button"
            className="ssi-pip-dismiss"
            aria-label="Hide Pip"
            onClick={() => {
              setEnabled(false);
              setSpeaking(false);
            }}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {!speaking && (
        <button
          className="ssi-pip-launcher"
          aria-label="Show Pip's guide"
          type="button"
          onClick={() => {
            setEnabled(true);
            setSpeaking(true);
            setTip(
              sectionTips[section] ?? "Let's explore StudentSuccessful together!"
            );
          }}
        >
          <span aria-hidden="true">✦</span> Ask Pip
        </button>
      )}
    </>
  );
}

export function InteractiveLanding() {
  const router = useRouter();
  const { refresh } = useAuth();
  const demoEnabled = isDemoModeEnabled();
  const configuredDemoOrigin = process.env.NEXT_PUBLIC_DEMO_DEPLOYMENT_URL?.trim();
  let demoDeploymentOrigin = "";
  if (configuredDemoOrigin) {
    try {
      const parsed = new URL(configuredDemoOrigin);
      if (parsed.protocol === "https:" || parsed.protocol === "http:") {
        demoDeploymentOrigin = parsed.origin;
      }
    } catch {
      // A missing or invalid deployment URL falls back to registration.
    }
  }
  const demoEntryHref = demoEnabled
    ? "/demo"
    : demoDeploymentOrigin
      ? `${demoDeploymentOrigin}/demo`
      : "/register";
  const hasInteractiveDemo = demoEnabled || Boolean(demoDeploymentOrigin);
  const initialWorkspace = useMemo(() => mockApi.getWorkspace(), []);
  const jobs = OFFICIAL_2027_JOBS;

  const [search, setSearch] = useState("");
  const [city, setCity] = useState("All locations");
  const [mode, setMode] = useState("All modes");
  const [selectedJob, setSelectedJob] = useState(
    initialWorkspace.selectedJobId || "amd-sw"
  );
  const [saved, setSaved] = useState<string[]>(initialWorkspace.savedJobIds);
  const [skills, setSkills] = useState<string[]>(initialWorkspace.profile.skills);
  const [version, setVersion] = useState<"v1" | "v2">(
    initialWorkspace.activeResumeId
  );
  const [applications, setApplications] = useState(
    initialWorkspace.applications.filter(
      (a): a is typeof a & { stage: Stage } =>
        a.stage === "Applied" || a.stage === "Interview" || a.stage === "Offer"
    )
  );
  const [demoNotice, setDemoNotice] = useState("");
  const [applicationFilter, setApplicationFilter] = useState("All");
  const [activeSection, setActiveSection] = useState("discover");
  const [menuOpen, setMenuOpen] = useState(false);
  const progressRef = useRef<HTMLDivElement>(null);
  const [introReplay, setIntroReplay] = useState(0);

  async function handleEnterDemo(
    e: React.MouseEvent<HTMLAnchorElement>,
    targetPath = "/demo"
  ) {
    if (!demoEnabled) {
      // Production never enters a local mock session. Link to the separately
      // deployed demo (when configured), otherwise direct users to sign up.
      e.preventDefault();
      window.location.assign(
        demoDeploymentOrigin ? `${demoDeploymentOrigin}${targetPath}` : "/register"
      );
      return;
    }
    e.preventDefault();
    activateDemoSession();
    try {
      await refresh();
    } catch {
      // Ignore refresh error in demo mode
    }
    router.push(targetPath || "/demo");
  }

  useEffect(() => {
    const elements = Array.from(
      document.querySelectorAll<HTMLElement>(".ssi-reveal")
    );
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("ssi-visible");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.08, rootMargin: "0px 0px -35px 0px" }
    );
    elements.forEach((el) => observer.observe(el));

    const sections = ["discover", "match", "resume", "track"]
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => Boolean(el));
    const navObserver = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) setActiveSection(e.target.id);
        }),
      { rootMargin: "-18% 0px -55% 0px" }
    );
    sections.forEach((el) => navObserver.observe(el));

    const onScroll = () => {
      const doc = document.documentElement;
      const possible = doc.scrollHeight - window.innerHeight;
      progressRef.current?.style.setProperty(
        "transform",
        `scaleX(${possible > 0 ? Math.min(1, window.scrollY / possible) : 0})`
      );
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    return () => {
      observer.disconnect();
      navObserver.disconnect();
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  const filtered = useMemo(
    () =>
      jobs.filter(
        (j) =>
          [j.title, j.company, ...j.requirements]
            .join(" ")
            .toLowerCase()
            .includes(search.trim().toLowerCase()) &&
          (city === "All locations" || j.city === city) &&
          (mode === "All modes" || j.mode === mode)
      ),
    [jobs, search, city, mode]
  );

  const selected = jobs.find((j) => j.id === selectedJob) || jobs[0];
  const examples = Array.from(
    new Set([...selected.requirements, "React", "Python", "PostgreSQL", "TypeScript"])
  ).slice(0, 9);

  const covered = selected.requirements.filter((x) => skills.includes(x));
  const gaps = selected.requirements.filter((x) => !skills.includes(x));

  const activeResumeRecord = useMemo(() => {
    const ws = mockApi.getWorkspace();
    return ws.resumes.find((r) => r.id === version);
  }, [version]);

  const presented = useMemo(() => {
    if (activeResumeRecord) {
      return selected.requirements.filter((req) =>
        activeResumeRecord.includedSkills.includes(req)
      );
    }
    return version === "v1"
      ? selected.requirements.slice(0, 1)
      : selected.requirements.slice(0, 3);
  }, [activeResumeRecord, selected.requirements, version]);

  const onResume = selected.requirements.filter((s) => presented.includes(s));
  const inProfile = selected.requirements.filter(
    (s) => !presented.includes(s) && skills.includes(s)
  );
  const missing = selected.requirements.filter(
    (s) => !presented.includes(s) && !skills.includes(s)
  );
  const filteredApps = applications.filter(
    (a) => applicationFilter === "All" || a.stage === applicationFilter
  );

  function toggleSaved(id: string) {
    const updated = mockApi.toggleSaveJob(id);
    setSaved(updated.savedJobIds);
  }

  function toggleSkill(skill: string) {
    const updated = mockApi.toggleProfileSkill(skill);
    setSkills(updated.profile.skills);
  }

  function handleSelectVersion(v: "v1" | "v2") {
    mockApi.setActiveResume(v);
    setVersion(v);
  }

  function markAsApplied(job: InternshipJob) {
    const updated = mockApi.addJobToTracker(job, "Applied");
    setApplications(
      updated.applications.filter(
        (a): a is typeof a & { stage: Stage } =>
          a.stage === "Applied" || a.stage === "Interview" || a.stage === "Offer"
      )
    );
    setDemoNotice(
      `${job.company} role added to the tracker. To submit an application, follow the employer link.`
    );
  }

  function updateStage(id: string, stage: Stage) {
    const updated = mockApi.updateApplicationStage(id, stage as ApplicationStage);
    setApplications(
      updated.applications.filter(
        (a): a is typeof a & { stage: Stage } =>
          a.stage === "Applied" || a.stage === "Interview" || a.stage === "Offer"
      )
    );
  }

  const closeMenu = () => setMenuOpen(false);

  return (
    <main className="ssi-page">
      <OfferIntro replaySignal={introReplay} />
      <div className="ssi-scroll-progress" ref={progressRef} aria-hidden="true" />
      <CareerGuide section={activeSection} />

      <header className="ssi-header">
        <nav className="ssi-container ssi-nav" aria-label="Public navigation">
          <Link href="/" className="ssi-brand" aria-label="StudentSuccessful home">
            <Image
              src="/brand/studentsuccessful-horizontal-transparent.png"
              alt="StudentSuccessful"
              width={204}
              height={67}
              className="ssi-brand-lockup"
              unoptimized
            />
          </Link>

          <div className={`ssi-nav-links${menuOpen ? " is-open" : ""}`}>
            <a
              onClick={closeMenu}
              href="#discover"
              aria-current={activeSection === "discover" ? "location" : undefined}
            >
              Job discovery
            </a>
            <a
              onClick={closeMenu}
              href="#match"
              aria-current={activeSection === "match" ? "location" : undefined}
            >
              Fit insights
            </a>
            <a
              onClick={closeMenu}
              href="#resume"
              aria-current={activeSection === "resume" ? "location" : undefined}
            >
              Resumes
            </a>
            <a
              onClick={closeMenu}
              href="#track"
              aria-current={activeSection === "track" ? "location" : undefined}
            >
              Tracker
            </a>
          </div>

          <div className="ssi-nav-right">
            <button
              type="button"
              className="ssi-intro-replay"
              aria-label="Replay the welcome email animation"
              onClick={() => setIntroReplay((v) => v + 1)}
            >
              <MailOpen size={15} />
              <span>Replay intro</span>
            </button>
            {!demoEnabled && <Link href="/login" className="ssi-login" aria-label="Sign in">Sign in</Link>}
            <Link
              href={demoEntryHref}
              onClick={(e) => {
                void handleEnterDemo(e, "/demo");
              }}
              className="ssi-button ssi-button-black ssi-try-demo-cta"
            >
              {hasInteractiveDemo ? "Try interactive demo" : "Get started"} <ArrowUpRight size={15} />
            </Link>
            <button
              className="ssi-mobile-toggle"
              type="button"
              aria-label={menuOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((v) => !v)}
            >
              {menuOpen ? <X size={22} /> : <Menu size={22} />}
            </button>
          </div>
        </nav>
      </header>

      <section className="ssi-hero" aria-labelledby="ssi-hero-title">
        <div className="ssi-hero-glow" aria-hidden="true" />
        <div className="ssi-container ssi-hero-grid">
          <Reveal className="ssi-hero-copy">
            <div className="ssi-kicker">
              <span className="ssi-green-dot" /> THE CAREER WORKSPACE FOR STUDENTS
            </div>
            <h1 id="ssi-hero-title">
              Find a role worth applying to.{" "}
              <em>Know what to do next.</em>
            </h1>
            <p>
              Compare job requirements with your saved experience, keep resumes focused,
              and track each application from the first step onward.
            </p>
            <div className="ssi-actions">
              <Link
                className="ssi-button ssi-button-indigo ssi-button-big ssi-try-demo-cta"
                href={demoEntryHref}
                onClick={(e) => {
                  void handleEnterDemo(e, "/demo");
                }}
              >
                <Play size={16} fill="currentColor" /> {hasInteractiveDemo ? "Try interactive demo" : "Get started"}{" "}
                <ArrowRight size={17} />
              </Link>
              <a
                className="ssi-button ssi-button-outline ssi-button-big"
                href="#discover"
              >
                See how it works <ArrowDownRight size={17} />
              </a>
            </div>
            <div className="ssi-hero-trail">
              <span>
                <CheckCircle2 size={15} /> Official employer application links
              </span>
              <span>
                <ShieldCheck size={15} /> Evidence-based requirement breakdown
              </span>
            </div>
          </Reveal>

          <Reveal className="ssi-hero-stage">
            <div className="ssi-stage-halo" />
            <div className="ssi-browser">
              <div className="ssi-browser-top">
                <span className="ssi-dots">
                  <i />
                  <i />
                  <i />
                </span>
                <span>studentsuccessful / workspace</span>
                <PanelTop size={15} />
              </div>
              <div className="ssi-browser-content">
                <div className="ssi-browser-greeting">
                  <small>YOUR WORKSPACE</small>
                  <strong>Find your next opportunity.</strong>
                  <span>
                    From job requirements to your next application step.
                  </span>
                </div>
                <div className="ssi-browser-quick">
                  <a href="#discover">
                    <span className="ssi-icon-tile">
                      <Search size={18} />
                    </span>
                    <small>DISCOVER</small>
                    <b>Browse roles</b>
                  </a>
                  <a href="#match">
                    <span className="ssi-icon-tile">
                      <Target size={18} />
                    </span>
                    <small>UNDERSTAND</small>
                    <b>Trace evidence</b>
                  </a>
                  <a href="#track">
                    <span className="ssi-icon-tile">
                      <FileCheck2 size={18} />
                    </span>
                    <small>ORGANIZE</small>
                    <b>Track progress</b>
                  </a>
                </div>
                <button
                  type="button"
                  className="ssi-browser-row"
                  onClick={() => {
                    setSelectedJob("amd-sw");
                    document
                      .getElementById("discover")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  <BrandLogo brand="amd" company="AMD" />
                  <div>
                    <strong>2027 Software Engineering Co-Op</strong>
                    <span>AMD · Markham, ON</span>
                  </div>
                  <span className="ssi-browser-state">Saved</span>
                </button>
                <button
                  type="button"
                  className="ssi-browser-row"
                  onClick={() => {
                    setSelectedJob("nvidia-sw");
                    document
                      .getElementById("discover")
                      ?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  <BrandLogo brand="nvidia" company="NVIDIA" />
                  <div>
                    <strong>2027 Software Engineering Intern</strong>
                    <span>NVIDIA · Santa Clara, CA</span>
                  </div>
                  <ChevronRight size={17} />
                </button>
              </div>
            </div>
            <div className="ssi-float-card">
              <span className="ssi-float-icon">
                <Check size={17} />
              </span>
              <div>
                <b>One place to stay organized</b>
                <small>Jobs, resumes, and applications together</small>
              </div>
            </div>
          </Reveal>
        </div>

        <div
          className="ssi-container ssi-hero-bottom"
          aria-label="Core career workflow steps"
        >
          <div className="ssi-hero-marquee">
            <div className="ssi-hero-marquee-track">
              <div className="ssi-hero-marquee-group">
                <a href="#discover" className="ssi-hero-step-pill">
                  <span className="ssi-hero-step-num">01</span>
                  <span>Browse 2027 internships</span>
                </a>
                <a href="#match" className="ssi-hero-step-pill">
                  <span className="ssi-hero-step-num">02</span>
                  <span>Compare roles with your skills</span>
                </a>
                <a href="#resume" className="ssi-hero-step-pill">
                  <span className="ssi-hero-step-num">03</span>
                  <span>Check your resume versions</span>
                </a>
                <a href="#track" className="ssi-hero-step-pill">
                  <span className="ssi-hero-step-num">04</span>
                  <span>Track applications</span>
                </a>
              </div>
              <div className="ssi-hero-marquee-group" aria-hidden="true">
                <a href="#discover" className="ssi-hero-step-pill" tabIndex={-1}>
                  <span className="ssi-hero-step-num">01</span>
                  <span>Browse 2027 internships</span>
                </a>
                <a href="#match" className="ssi-hero-step-pill" tabIndex={-1}>
                  <span className="ssi-hero-step-num">02</span>
                  <span>Compare roles with your skills</span>
                </a>
                <a href="#resume" className="ssi-hero-step-pill" tabIndex={-1}>
                  <span className="ssi-hero-step-num">03</span>
                  <span>Check your resume versions</span>
                </a>
                <a href="#track" className="ssi-hero-step-pill" tabIndex={-1}>
                  <span className="ssi-hero-step-num">04</span>
                  <span>Track applications</span>
                </a>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section id="discover" className="ssi-story ssi-story-cream">
        <div className="ssi-container ssi-story-grid">
          <Reveal className="ssi-story-intro">
            <div className="ssi-chapter">
              <span>01 / DISCOVERY</span>
              <span className="ssi-chapter-rule" />
            </div>
            <h2>
              Stop collecting tabs. <em>Start finding direction.</em>
            </h2>
            <p>
              Browse selected internship and co-op roles. Filter by location or work
              style, check what each role asks for, and follow the employer link
              to confirm the current posting.
            </p>
            <div className="ssi-story-points">
              <span>
                <Search size={16} /> Search internships by company, title, or
                technical skill
              </span>
              <span>
                <Bookmark size={16} /> Save promising roles to your personal
                shortlist
              </span>
              <span>
                <MapPin size={16} /> Apply directly on official company career
                portals
              </span>
            </div>
            <a className="ssi-text-link" href="#match">
              Next: compare role requirements with your profile{" "}
              <ArrowDownRight size={17} />
            </a>
          </Reveal>

          <Reveal className="ssi-demo-card ssi-discover-demo">
            <div className="ssi-demo-head">
              <div>
                <span className="ssi-demo-eyebrow">
                  INTERNSHIP ROLE EXAMPLES · 2027
                </span>
                <h3>Browse internship roles</h3>
              </div>
            </div>

            <div className="ssi-searchbar">
              <Search size={18} />
              <input
                aria-label="Search sample opportunities"
                placeholder="Search AMD, NVIDIA, Python, C++, Markham..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {search && (
                <button
                  className="ssi-clear"
                  aria-label="Clear search"
                  onClick={() => setSearch("")}
                  type="button"
                >
                  <X size={16} />
                </button>
              )}
            </div>

            <div className="ssi-filterbar">
              <label>
                Location
                <select value={city} onChange={(e) => setCity(e.target.value)}>
                  <option>All locations</option>
                  <option>Markham</option>
                  <option>Toronto</option>
                  <option>Vancouver</option>
                  <option>Santa Clara</option>
                </select>
              </label>
              <label>
                Work style
                <select value={mode} onChange={(e) => setMode(e.target.value)}>
                  <option>All modes</option>
                  <option>On-site</option>
                  <option>Not specified</option>
                </select>
              </label>
              <span className="ssi-result-count">{filtered.length} roles</span>
            </div>

            <div className="ssi-job-intro">
              <span>
                <CheckCircle2 size={15} /> Direct employer career links
              </span>
              <span>2027 internships · Canada &amp; US</span>
            </div>

            <div className="ssi-jobs-stack" aria-label="Job search results">
              {filtered.length === 0 ? (
                <div className="ssi-empty">
                  No roles match your current filters. Try clearing your search.
                </div>
              ) : (
                filtered.map((job) => (
                  <div
                    key={job.id}
                    data-job-id={job.id}
                    className={`ssi-job-item${
                      selectedJob === job.id ? " is-selected" : ""
                    }`}
                  >
                    <button
                      type="button"
                      className="ssi-job-main"
                      aria-pressed={selectedJob === job.id}
                      onClick={() => {
                        setSelectedJob(job.id);
                        mockApi.selectJob(job.id);
                        setDemoNotice("");
                      }}
                    >
                      <BrandLogo brand={job.brand} company={job.company} />
                      <span>
                        <b>{job.title}</b>
                        <small>
                          {job.company} <span aria-hidden="true">·</span>{" "}
                          {job.city} · {job.mode}
                        </small>
                        <span className="ssi-job-term">{job.term}</span>
                      </span>
                    </button>
                    <button
                      type="button"
                      className={`ssi-save${
                        saved.includes(job.id) ? " is-saved" : ""
                      }`}
                      aria-label={`${
                        saved.includes(job.id) ? "Remove saved" : "Save"
                      } ${job.title}`}
                      aria-pressed={saved.includes(job.id)}
                      onClick={() => toggleSaved(job.id)}
                    >
                      <Bookmark
                        size={17}
                        fill={saved.includes(job.id) ? "currentColor" : "none"}
                      />
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="ssi-detail-preview">
              <div className="ssi-detail-top">
                <BrandLogo brand={selected.brand} company={selected.company} />
                <div>
                  <small>SELECTED ROLE · {selected.company}</small>
                  <strong>{selected.title}</strong>
                  <span>
                    {selected.city}, {selected.country} · {selected.mode}
                  </span>
                </div>
              </div>
              <p>{selected.short}</p>
              <div className="ssi-chip-row">
                {selected.requirements.map((s) => (
                  <span key={s}>{s}</span>
                ))}
              </div>
              <div className="ssi-job-meta">
                <span>Posting ID: {selected.reqId}</span>
                <span>{selected.term}</span>
              </div>
              <div className="ssi-detail-actions">
                <a
                  href={selected.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ssi-external-apply"
                >
                  Apply at {selected.company} <ArrowUpRight size={15} />
                </a>
                <button
                  type="button"
                  className="ssi-mark-applied"
                  onClick={() => markAsApplied(selected)}
                >
                  <Check size={15} /> Add to application tracker
                </button>
              </div>
              {demoNotice && (
                <p className="ssi-demo-notice" role="status">
                  {demoNotice}
                </p>
              )}
            </div>

            <div className="ssi-demo-footer">
              <span>
                <Bookmark size={15} /> {saved.length} saved in shortlist
              </span>
              <Link
                href="/jobs"
                onClick={(e) => {
                  void handleEnterDemo(e, "/jobs");
                }}
              >
                Open Job Discovery <ArrowRight size={15} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="match" className="ssi-story ssi-story-slate">
        <div className="ssi-container ssi-story-grid ssi-reversed">
          <Reveal className="ssi-story-intro">
            <div className="ssi-chapter">
              <span>02 / EVIDENCE</span>
              <span className="ssi-chapter-rule" />
            </div>
            <h2>
              Know what you have. <em>See what needs proof.</em>
            </h2>
            <p>
              Instead of guessing whether you qualify—or relying on arbitrary
              match percentages—compare each requirement directly against the
              skills recorded in your projects, coursework, and work history.
            </p>
            <div className="ssi-story-points">
              <span>
                <ShieldCheck size={16} /> Grounded in your recorded projects and
                coursework
              </span>
              <span>
                <Target size={16} /> Clear distinction between supported skills
                and open gaps
              </span>
              <span>
                <Layers3 size={16} /> Reusable qualification profile across every
                application
              </span>
            </div>
            <a className="ssi-text-link" href="#resume">
              Next: verify what appears on your resume{" "}
              <ArrowDownRight size={17} />
            </a>
          </Reveal>

          <Reveal className="ssi-demo-card ssi-fit-demo">
            <div className="ssi-demo-head">
              <div>
                <span className="ssi-demo-eyebrow">CANDIDATE–JOB FIT</span>
                <h3>What does this role require?</h3>
              </div>
            </div>
            <p className="ssi-demo-context">
              Comparing against <b>{selected.title}</b> ({selected.company})
            </p>
            <p className="ssi-control-label">
              Toggle skills recorded in your sample profile
            </p>
            <div className="ssi-toggle-row">
              {examples.map((s) => (
                <button
                  data-skill={s}
                  className={`ssi-skill-toggle${
                    skills.includes(s) ? " is-selected" : ""
                  }`}
                  aria-pressed={skills.includes(s)}
                  key={s}
                  type="button"
                  onClick={() => toggleSkill(s)}
                >
                  {skills.includes(s) ? (
                    <Check size={14} />
                  ) : (
                    <span className="ssi-toggle-plus">+</span>
                  )}
                  {s}
                </button>
              ))}
            </div>

            <div className="ssi-evidence-grid">
              <div className="ssi-evidence-supported">
                <div className="ssi-evidence-title">
                  <CheckCircle2 size={17} /> Recorded evidence{" "}
                  <b>{covered.length}</b>
                </div>
                {covered.length ? (
                  covered.map((s) => (
                    <div className="ssi-evidence-item" key={s}>
                      <span>{s}</span>
                      <small>In profile</small>
                    </div>
                  ))
                ) : (
                  <p className="ssi-evidence-empty">
                    No requirements for this role are selected yet.
                  </p>
                )}
              </div>
              <div className="ssi-evidence-unknown">
                <div className="ssi-evidence-title">
                  <CircleHelp size={17} /> Needs evidence <b>{gaps.length}</b>
                </div>
                {gaps.length ? (
                  gaps.map((s) => (
                    <div className="ssi-evidence-item" key={s}>
                      <span>{s}</span>
                      <small>Not recorded</small>
                    </div>
                  ))
                ) : (
                  <p className="ssi-evidence-empty">
                    Every listed requirement has supporting evidence in your
                    profile.
                  </p>
                )}
              </div>
            </div>

            <div className="ssi-demo-footer">
              <span>
                {covered.length} of {selected.requirements.length} core
                requirements supported
              </span>
              <Link
                href={`/jobs/${selected.id}/fit`}
                onClick={(e) => {
                  void handleEnterDemo(e, `/jobs/${selected.id}/fit`);
                }}
              >
                Open Fit Analysis <ArrowRight size={15} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="resume" className="ssi-story ssi-story-white">
        <div className="ssi-container ssi-story-grid">
          <Reveal className="ssi-story-intro">
            <div className="ssi-chapter">
              <span>03 / RESUME ALIGNMENT</span>
              <span className="ssi-chapter-rule" />
            </div>
            <h2>
              A skill in your profile is not{" "}
              <em>automatically on your resume.</em>
            </h2>
            <p>
              Students often have strong project experience that never makes it
              onto the specific PDF they submit. Compare your saved resume
              versions against the job description before you apply.
            </p>
            <div className="ssi-story-points">
              <span>
                <FileSearch size={16} /> Compare tailored resume versions side
                by side
              </span>
              <span>
                <Database size={16} /> Spot qualifications recorded in your
                profile but omitted from a file
              </span>
              <span>
                <FilePenLine size={16} /> Know exactly which bullets to tighten
                before submitting
              </span>
            </div>
            <a className="ssi-text-link" href="#track">
              Next: keep every application moving forward{" "}
              <ArrowDownRight size={17} />
            </a>
          </Reveal>

          <Reveal className="ssi-demo-card ssi-resume-demo">
            <div className="ssi-demo-head">
              <div>
                <span className="ssi-demo-eyebrow">RESUME ALIGNMENT</span>
                <h3>Your resume, in context</h3>
              </div>
            </div>

            <div className="ssi-version-bar">
              <div className="ssi-file-glyph">
                <FileCheck2 size={20} />
              </div>
              <div>
                <strong>
                  {version === "v2"
                    ? "Systems & Full-Stack Resume (v2)"
                    : "General Software Engineer Resume (v1)"}
                </strong>
                <span>
                  Comparing against {selected.company} · {selected.title}
                </span>
              </div>
              <div className="ssi-version-switch">
                <button
                  type="button"
                  aria-pressed={version === "v1"}
                  data-version="v1"
                  onClick={() => handleSelectVersion("v1")}
                >
                  v1
                </button>
                <button
                  type="button"
                  aria-pressed={version === "v2"}
                  data-version="v2"
                  onClick={() => handleSelectVersion("v2")}
                >
                  v2
                </button>
              </div>
            </div>

            <div className="ssi-resume-groups">
              <div className="ssi-resume-group">
                <span className="ssi-pill positive">Shown on resume</span>
                <div className="ssi-tag-cloud">
                  {onResume.length ? (
                    onResume.map((s) => <span key={s}>{s}</span>)
                  ) : (
                    <small>None included in this version</small>
                  )}
                </div>
              </div>
              <div className="ssi-resume-group">
                <span className="ssi-pill warning">
                  In profile, not on this file
                </span>
                <div className="ssi-tag-cloud">
                  {inProfile.length ? (
                    inProfile.map((s) => <span key={s}>{s}</span>)
                  ) : (
                    <small>All profile skills are included</small>
                  )}
                </div>
              </div>
              <div className="ssi-resume-group">
                <span className="ssi-pill muted">Unconfirmed / missing</span>
                <div className="ssi-tag-cloud">
                  {missing.length ? (
                    missing.map((s) => <span key={s}>{s}</span>)
                  ) : (
                    <small>No remaining skill gaps</small>
                  )}
                </div>
              </div>
            </div>

            <div className="ssi-resume-tip">
              <FileSearch size={18} />
              <p>
                Evidence is separated by source. Switching from{" "}
                <strong>v1</strong> to <strong>v2</strong> shows how a
                systems-focused resume covers C/C++ and Linux requirements.
              </p>
            </div>

            <div className="ssi-demo-footer">
              <span>
                Resume {version} · {onResume.length} of{" "}
                {selected.requirements.length} requirements shown on file
              </span>
              <Link
                href={`/jobs/${selected.id}/resume-alignment`}
                onClick={(e) => {
                  void handleEnterDemo(
                    e,
                    `/jobs/${selected.id}/resume-alignment`
                  );
                }}
              >
                Open Resume Alignment <ArrowRight size={15} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section id="track" className="ssi-story ssi-story-soft">
        <div className="ssi-container ssi-story-grid ssi-reversed">
          <Reveal className="ssi-story-intro">
            <div className="ssi-chapter">
              <span>04 / APPLICATION TRACKER</span>
              <span className="ssi-chapter-rule" />
            </div>
            <h2>
              Applications should move forward. <em>Not disappear.</em>
            </h2>
            <p>
              Keep your active applications, interview stages, and preparation
              notes in one structured view—without maintaining fragile
              spreadsheets across recruiting seasons.
            </p>
            <div className="ssi-story-points">
              <span>
                <Clock3 size={16} /> Track every stage from Applied to Interview
                and Offer
              </span>
              <span>
                <CheckCircle2 size={16} /> Instant status updates and filtering
              </span>
              <span>
                <Layers3 size={16} /> Connected to the resume version and role
                details you used
              </span>
            </div>
            <Link
              href="/applications"
              onClick={(e) => {
                void handleEnterDemo(e, "/applications");
              }}
              className="ssi-text-link"
            >
              Open the full interactive workspace <ArrowUpRight size={17} />
            </Link>
          </Reveal>

          <Reveal className="ssi-demo-card ssi-track-demo">
            <div className="ssi-demo-head">
              <div>
                <span className="ssi-demo-eyebrow">APPLICATION PIPELINE</span>
                <h3>Keep the momentum</h3>
              </div>
            </div>

            <div className="ssi-track-summary">
              <div>
                <b>{applications.length}</b>
                <span>Tracked</span>
              </div>
              <div>
                <b>
                  {applications.filter((a) => a.stage === "Interview").length}
                </b>
                <span>Interviews</span>
              </div>
              <div>
                <b>{applications.filter((a) => a.stage === "Offer").length}</b>
                <span>Offers</span>
              </div>
            </div>

            <div className="ssi-track-filters">
              {["All", ...stages].map((f) => (
                <button
                  key={f}
                  type="button"
                  data-filter={f}
                  aria-pressed={applicationFilter === f}
                  onClick={() => setApplicationFilter(f)}
                >
                  {f}
                </button>
              ))}
            </div>

            <div className="ssi-app-list">
              {filteredApps.length ? (
                filteredApps.map((app) => (
                  <div
                    className="ssi-app-row"
                    data-application={app.id}
                    key={app.id}
                  >
                    <div className="ssi-app-ident">
                      <span className="ssi-app-dot" />
                      <div>
                        <strong>{app.role}</strong>
                        <small>
                          {app.company} · {app.date}
                        </small>
                      </div>
                    </div>
                    <label>
                      <span className="ssi-sr-only">
                        Application stage for {app.role}
                      </span>
                      <select
                        value={app.stage}
                        onChange={(e) =>
                          updateStage(app.id, e.target.value as Stage)
                        }
                      >
                        {stages.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </label>
                  </div>
                ))
              ) : (
                <div className="ssi-empty">
                  No applications in this stage.
                </div>
              )}
            </div>

            <div className="ssi-demo-footer">
              <span>Application stages and private interview notes</span>
              <Link
                href="/applications"
                onClick={(e) => {
                  void handleEnterDemo(e, "/applications");
                }}
              >
                Open Application Tracker <ArrowRight size={15} />
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="ssi-bottom" id="get-started">
        <div className="ssi-container">
          <Reveal className="ssi-final">
            <span className="ssi-kicker ssi-bottom-kicker">YOUR NEXT MOVE</span>
            <h2>
              Know what a role needs. <em>Keep your next step in view.</em>
            </h2>
            <p>
              Explore how to organize your roles, resumes, and applications in one workspace.
            </p>
            <div className="ssi-actions">
              <Link
                className="ssi-button ssi-button-white ssi-button-big ssi-try-demo-cta"
                href={demoEntryHref}
                onClick={(e) => {
                  void handleEnterDemo(e, "/demo");
                }}
              >
                {hasInteractiveDemo ? "Try interactive demo" : "Get started"} <ArrowUpRight size={18} />
              </Link>
              {!demoEnabled && (<Link
                className="ssi-button ssi-button-bottom-outline ssi-button-big"
                href="/register"
                aria-label="Create account"
              >
                Create account <ArrowRight size={17} />
              </Link>)}
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="ssi-footer">
        <div className="ssi-container ssi-footer-layout">
          <Link href="/" className="ssi-brand">
            <Image
              src="/brand/studentsuccessful-horizontal-transparent.png"
              alt="StudentSuccessful"
              width={192}
              height={63}
              className="ssi-brand-lockup"
              unoptimized
            />
          </Link>
          <p>
            Find roles, review requirements, and keep your applications in order.
          </p>
          <div className="ssi-footer-links">
            <a href="#discover">Job discovery</a>
            <a href="#match">Fit insights</a>
            <a href="#resume">Resumes</a>
            <a href="#track">Tracker</a>
            <Link
              href={demoEntryHref}
              onClick={(e) => {
                void handleEnterDemo(e, "/demo");
              }}
            >
              {hasInteractiveDemo ? "Interactive demo" : "Get started"}
            </Link>
            {!demoEnabled && (<><Link href="/login">Sign in</Link>
            <Link href="/register">Create account</Link></>)}
          </div>
          <small>
            Sample interactions use illustrative student data. Official career
            links lead to third-party employer websites; posting availability
            may change. StudentSuccessful is not affiliated with or endorsed by
            listed employers.
          </small>
        </div>
      </footer>
    </main>
  );
}
