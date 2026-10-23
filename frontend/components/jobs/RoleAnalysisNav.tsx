import Link from "next/link";

type View = "fit" | "resume-alignment" | "gaps" | "resume-plan" | "resume-draft";

const steps: Array<{ view: View; label: string }> = [
  { view: "fit", label: "Profile fit" },
  { view: "resume-alignment", label: "Resume coverage" },
  { view: "gaps", label: "Evidence gaps" },
  { view: "resume-plan", label: "Improvement plan" },
  { view: "resume-draft", label: "Draft suggestions" },
];

/** Keep users oriented as they compare the same role across several views. */
export function RoleAnalysisNav({ jobId, selected, versionId }: {
  jobId: string;
  selected: View;
  versionId?: string | null;
}) {
  const base = "/jobs/" + encodeURIComponent(jobId);
  const versionQuery = versionId ? "?resume_version_id=" + encodeURIComponent(versionId) : "";
  return (
    <nav aria-label="Compare this job" className="role-analysis-nav">
      <span className="role-analysis-nav-label">REVIEW THIS ROLE</span>
      <div className="role-analysis-steps">
        {steps.map(({ view, label }) => (
          <Link
            key={view}
            href={base + "/" + view + (view === "fit" ? "" : versionQuery)}
            aria-current={selected === view ? "page" : undefined}
            className={selected === view ? "role-analysis-step is-active" : "role-analysis-step"}
          >{label}</Link>
        ))}
      </div>
    </nav>
  );
}
