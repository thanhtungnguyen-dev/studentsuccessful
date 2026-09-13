import Link from "next/link";
import { REVIEW_PATH } from "../../lib/onboarding/review";
export function ReturnToReview() {
  return <p className="review-return"><Link href={REVIEW_PATH}>Return to onboarding review</Link><span className="muted"> Save any edits before returning.</span></p>;
}
