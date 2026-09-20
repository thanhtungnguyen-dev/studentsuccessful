"use client";

import { useEffect, useRef, type CSSProperties, type HTMLAttributes } from "react";

type RevealProps = HTMLAttributes<HTMLElement> & {
  as?: "div" | "section" | "header";
  delay?: number;
  direction?: "up" | "down" | "none";
};

/** Content is visible by default, including SSR and browsers without observers. */
export function Reveal({ as: Tag = "div", delay = 0, direction = "up", className = "", style, ...props }: RevealProps) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        element.classList.add("is-revealed");
        observer.disconnect();
      }
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return <Tag ref={ref as React.Ref<HTMLDivElement>} className={`reveal ${className}`} data-direction={direction}
    style={{ ...style, "--reveal-delay": `${Math.min(Math.max(delay, 0), 240)}ms` } as CSSProperties} {...props} />;
}
