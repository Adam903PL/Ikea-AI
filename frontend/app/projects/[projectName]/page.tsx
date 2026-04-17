import type { Metadata } from "next";
import { notFound } from "next/navigation";
import StepViewer from "@/app/_components/step-viewer";
import { fetchProjectDetails, getPrimaryStepPath } from "@/app/_lib/api";
import ProjectDetail from "@/app/_components/project-detail";

type ProjectPageProps = {
  params: Promise<{
    projectName: string;
  }>;
};

export async function generateMetadata({
  params,
}: ProjectPageProps): Promise<Metadata> {
  const { projectName } = await params;
  const decodedProjectName = decodeURIComponent(projectName);

  return {
    title: `${decodedProjectName} | Projekty | IKEA 3D Manager`,
  };
}

export default async function ProjectPage({ params }: ProjectPageProps) {
  const { projectName } = await params;
  const decodedProjectName = decodeURIComponent(projectName);
  const project = await fetchProjectDetails(decodedProjectName);

  if (!project) {
    notFound();
  }

  const primaryStepPath = getPrimaryStepPath(project);
  const meshUrl = project.mesh_url ?? null;

  return (
    <ProjectDetail project={project} primaryStepPath={primaryStepPath}>
      {meshUrl ? (
        <StepViewer projectName={project.object_name} meshUrl={meshUrl} />
      ) : (
        <div
          className="flex h-[520px] items-center justify-center rounded-2xl text-sm"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            color: "var(--foreground-muted)",
          }}
        >
          Projekt nie ma jeszcze przygotowanej geometrii 3D.
        </div>
      )}
    </ProjectDetail>
  );
}
