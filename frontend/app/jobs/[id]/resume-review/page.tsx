import { ResumeTailoringReviewPage } from "../../../../components/jobs/ResumeTailoringReviewPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResumeTailoringReviewPage jobId={id} />;
}
