import type { Metadata } from "next";
import ProjectsDashboard from "@/app/_components/projects-dashboard";

export const metadata: Metadata = {
  title: "Projekty | IKEA 3D Manager",
};

export default function ProjectsPage() {
  return <ProjectsDashboard />;
}
