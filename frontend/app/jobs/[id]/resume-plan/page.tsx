import { ResumeImprovementPlanPage } from "../../../../components/jobs/ResumeImprovementPlanPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResumeImprovementPlanPage jobId={id} />;
}
