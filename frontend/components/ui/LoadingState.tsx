import { Skeleton } from "./skeleton";

export function LoadingState({ label }: { label: string }) {
  return <div className="loading-state" role="status"><span className="sr-only">{label}</span><Skeleton /><Skeleton className="skeleton-short" /></div>;
}
