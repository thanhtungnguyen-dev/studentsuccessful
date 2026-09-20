import type { ReactNode } from "react";
import { Reveal } from "./Reveal";

export function PageHeader({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <Reveal as="header" className="page-header">
    <div><p className="eyebrow">YOUR CAREER WORKSPACE</p><h1 className="profile-title">{title}</h1>
      {description && <p className="muted">{description}</p>}</div>
    {children && <div className="page-header-actions">{children}</div>}
  </Reveal>;
}
