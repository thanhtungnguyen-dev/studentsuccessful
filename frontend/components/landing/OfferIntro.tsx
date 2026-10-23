"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Mail, X } from "lucide-react";

type IntroStep = "checking" | "envelope" | "letter" | "question" | "exit" | "done";

const STORAGE_KEY = "studentsuccessful-offer-intro-seen-v1";

const STEP_TIMINGS: Partial<Record<IntroStep, [IntroStep, number]>> = {
  envelope: ["letter", 960],
  letter: ["question", 2100],
  question: ["exit", 1150],
  exit: ["done", 700],
};

/** A fictional future-offer vignette, only for the public landing. */
export function OfferIntro({ replaySignal }: { replaySignal: number }) {
  const [step, setStep] = useState<IntroStep>("checking");
  const skipRef = useRef<HTMLButtonElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    let seen = false;
    try {
      seen = sessionStorage.getItem(STORAGE_KEY) === "1";
    } catch {
      /* private browsing */
    }
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const isAutomated = typeof navigator !== "undefined" && navigator.webdriver === true;
    setStep(seen || reduceMotion || isAutomated ? "done" : "envelope");
  }, []);

  useEffect(() => {
    if (replaySignal === 0) return;
    setStep(
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "question"
        : "envelope"
    );
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
  }, [replaySignal]);

  useEffect(() => {
    const config = STEP_TIMINGS[step];
    if (!config) return;
    const id = window.setTimeout(() => setStep(config[0]), config[1]);
    return () => window.clearTimeout(id);
  }, [step]);

  useEffect(() => {
    if (step !== "done") return;
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* optional */
    }
    lastFocused.current?.focus({ preventScroll: true });
    lastFocused.current = null;
  }, [step]);

  useEffect(() => {
    if (step === "done") return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    if (step === "envelope") {
      lastFocused.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null;
      skipRef.current?.focus({ preventScroll: true });
    }
    const skip = (event: KeyboardEvent) => {
      if (event.key === "Escape") setStep("done");
      if (event.key === "Tab" && step !== "checking") {
        event.preventDefault();
        skipRef.current?.focus();
      }
    };
    document.addEventListener("keydown", skip);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", skip);
    };
  }, [step]);

  if (step === "done") return null;

  return (
    <div
      className="ssi-offer-intro"
      data-step={step}
      role="dialog"
      aria-modal="true"
      aria-label="A letter from your future"
    >
      <div className="ssi-offer-grain" aria-hidden="true" />
      <div className="ssi-offer-curtain ssi-offer-curtain-left" aria-hidden="true" />
      <div className="ssi-offer-curtain ssi-offer-curtain-right" aria-hidden="true" />
      <div className="ssi-offer-topbar">
        <span className="ssi-offer-brand">
          <Mail size={16} strokeWidth={1.9} /> A letter from your future
        </span>
        <button
          ref={skipRef}
          type="button"
          className="ssi-offer-skip"
          onClick={() => setStep("done")}
        >
          Skip intro <X size={15} aria-hidden="true" />
        </button>
      </div>
      <div className="ssi-offer-stage">
        <div className="ssi-offer-envelope" aria-hidden="true">
          <div className="ssi-offer-envelope-back" />
          <div className="ssi-offer-envelope-flap" />
          <div className="ssi-offer-envelope-front" />
          <div className="ssi-offer-envelope-seal">✦</div>
          <div className="ssi-offer-envelope-caption">YOU&apos;VE GOT MAIL</div>
        </div>
        <article className="ssi-offer-paper">
          <div className="ssi-offer-paper-top">
            <span className="ssi-offer-mail-icon">
              <Mail size={19} strokeWidth={1.9} />
            </span>
            <span className="ssi-offer-inbox">
              Inbox <b>•</b> A message for you
            </span>
          </div>
          <div className="ssi-offer-rule" />
          <div className="ssi-offer-meta">
            <span>From</span>
            <b>Your future</b>
          </div>
          <div className="ssi-offer-meta">
            <span>To</span>
            <b>Tung</b>
          </div>
          <div className="ssi-offer-rule" />
          <div className="ssi-offer-letter-body">
            <p className="ssi-offer-eyebrow">THE EMAIL YOU&apos;VE BEEN WORKING TOWARD</p>
            <h2>
              Congratulations,
              <br />
              <em>Tung.</em>
            </h2>
            <p className="ssi-offer-lead">You&apos;ve been selected for the role of</p>
            <div className="ssi-offer-job-title">
              Software Engineer Intern <span>✦</span>
            </div>
            <p className="ssi-offer-signoff">Every organized step leads here.</p>
          </div>
          <div className="ssi-offer-paper-edge" aria-hidden="true" />
        </article>
        <div className="ssi-offer-big-question">
          <span>YOUR NEXT CHAPTER</span>
          <h2>
            Want to be
            <br />
            <em>next?</em>
          </h2>
          <p>Turn the opportunity into your story.</p>
          <div className="ssi-offer-arrow">
            <ArrowUpRight size={22} />
          </div>
        </div>
      </div>
      <div className="ssi-offer-bottom" aria-hidden="true">
        <span>STUDENTSUCCESSFUL</span>
        <span>✦</span>
        <span>THE CAREER WORKSPACE FOR STUDENTS</span>
      </div>
    </div>
  );
}
