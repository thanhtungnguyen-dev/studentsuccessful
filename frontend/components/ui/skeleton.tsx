// Adapted from Watermelon UI's MIT-licensed skeleton. See THIRD_PARTY_NOTICES.md.
import type { ComponentProps } from "react";

export function Skeleton({ className = "", ...props }: ComponentProps<"div">) {
  return <div aria-hidden="true" data-slot="skeleton" className={`ui-skeleton ${className}`} {...props} />;
}
