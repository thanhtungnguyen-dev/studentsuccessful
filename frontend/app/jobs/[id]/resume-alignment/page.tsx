import { ResumeAlignmentPage } from "../../../../components/jobs/ResumeAlignmentPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResumeAlignmentPage jobId={id} />;
}
