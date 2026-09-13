// Adapted from Watermelon UI's MIT-licensed card. See THIRD_PARTY_NOTICES.md.
import type { ComponentProps } from "react";

export function Card({ className = "", ...props }: ComponentProps<"section">) {
  return <section data-slot="card" className={`ui-card ${className}`} {...props} />;
}
