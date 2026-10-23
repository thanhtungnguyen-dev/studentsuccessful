import type { ReactNode } from "react";

/** A stable heading shared by every workspace route; no entrance delay or
 * intersection observer on navigation-critical content. */
export function PageHeader({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <header className="page-header">
    <div><h1 className="profile-title">{title}</h1>{description && <p className="muted">{description}</p>}</div>
    {children && <div className="page-header-actions">{children}</div>}
  </header>;
}
