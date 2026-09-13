"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { ChevronDown, Pencil, type LucideIcon } from "lucide-react";

export function SummaryDisclosure({title, status, href, icon: Icon, children, profileControl = false}: {
  title: string; status: string; href: string; icon: LucideIcon; children: ReactNode; profileControl?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return <section className={`summary-row${profileControl ? " profile-control" : ""}`} data-open={open}>
    <div className="summary-header">
      <h3><button type="button" id={`${id}-trigger`} aria-expanded={open} aria-controls={`${id}-content`} onClick={() => setOpen(value => !value)}>
        <Icon size={18} aria-hidden="true" /><span className="summary-copy"><span className="summary-title">{title}</span><span className="summary-status">{status}</span></span><ChevronDown className="summary-chevron" size={18} aria-hidden="true" />
      </button></h3>
      <Link className="summary-edit" href={href} aria-label={`Edit ${title}`} title={profileControl ? `Edit ${title}` : undefined}>{profileControl ? <><Pencil className="profile-edit-icon" size={16} aria-hidden="true" /><span className="profile-edit-label">Edit</span></> : "Edit"}</Link>
    </div>
    <div id={`${id}-content`} role="region" aria-labelledby={`${id}-trigger`} className="summary-expansion" inert={!open} aria-hidden={!open}>
      <div className="summary-clip"><div className="summary-preview">{children}<Link className="action-link" href={href}>Manage {title}</Link></div></div>
    </div>
  </section>;
}
