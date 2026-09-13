import { SkillGapPage } from "../../../../components/jobs/SkillGapPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <SkillGapPage jobId={id} />;
}
