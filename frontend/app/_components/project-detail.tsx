"use client";

import Link from "next/link";
import { buildApiUrl } from "@/app/_lib/api";
import type { ProjectObject } from "@/app/_lib/types";
import AssemblyInstructionsSection from "@/app/_components/assembly-instructions-section";
import Parts2DSection from "@/app/_components/parts-2d-section";

type ProjectDetailProps = {
  project: ProjectObject;
  primaryStepPath: string | null;
  children: React.ReactNode;
};

export default function ProjectDetail({
  project,
  primaryStepPath,
  children,
}: ProjectDetailProps) {
  const canGenerateAssembly = Boolean(project.mesh_url);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section
        className="rounded-2xl p-6 md:p-8"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <Link
              href="/projects"
              className="inline-flex items-center gap-2 text-sm font-medium transition"
              style={{ color: "var(--foreground-muted)" }}
              onMouseEnter={(event) => {
                event.currentTarget.style.color = "var(--foreground)";
              }}
              onMouseLeave={(event) => {
                event.currentTarget.style.color = "var(--foreground-muted)";
              }}
            >
              <span>←</span>
              <span>Wróć do projektów</span>
            </Link>

            <div>
              <p
                className="font-mono text-[10px] uppercase tracking-[0.22em]"
                style={{ color: "var(--foreground-subtle)" }}
              >
                Szczegóły projektu
              </p>
              <h1
                className="mt-3 text-2xl font-semibold tracking-tight md:text-3xl"
                style={{ color: "var(--foreground)" }}
              >
                {project.object_name}
              </h1>
              <p
                className="mt-3 max-w-2xl text-sm leading-7 md:text-base"
                style={{ color: "var(--foreground-muted)" }}
              >
                Podgląd bazuje na geometrii zapisanej przez backend FastAPI po
                przetworzeniu pliku STEP. Kolejne sekcje budują na tych samych
                artefaktach: mesh, części 2D i instrukcji montażu.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[320px]">
            <MetricCard label="Liczba plików" value={String(project.files.length)} />
            <MetricCard
              label="Status analizy"
              value={project.mesh_ready ? "Model 3D gotowy" : "Model 3D w przygotowaniu"}
              accent={project.mesh_ready ? "var(--success)" : "var(--foreground-muted)"}
            />
          </div>
        </div>

        <div
          className="mt-6 rounded-xl p-5"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
          }}
        >
          <p
            className="text-sm font-semibold"
            style={{ color: "var(--foreground-muted)" }}
          >
            Pliki w projekcie
          </p>
          <div className="mt-4 grid gap-2 md:grid-cols-2">
            {project.files.map((file) => (
              <a
                key={file.file_name}
                href={buildApiUrl(file.download_url)}
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-lg px-4 py-3 text-sm transition"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground-muted)",
                }}
                onMouseEnter={(event) => {
                  event.currentTarget.style.borderColor = "var(--border-strong)";
                  event.currentTarget.style.color = "var(--foreground)";
                }}
                onMouseLeave={(event) => {
                  event.currentTarget.style.borderColor = "var(--border)";
                  event.currentTarget.style.color = "var(--foreground-muted)";
                }}
              >
                <span className="truncate pr-4 font-mono text-[12px]">
                  {file.file_name}
                </span>
                <span
                  className="text-xs font-semibold"
                  style={{ color: "var(--accent)" }}
                >
                  Pobierz ↓
                </span>
              </a>
            ))}
          </div>

          <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium">
            <StatusChip
              active={project.mesh_ready}
              activeLabel="Mesh 3D zapisany"
              idleLabel="Mesh 3D przygotuje się po uploadzie"
            />
            <StatusChip
              active={project.parts_2d_ready}
              activeLabel="Części 2D gotowe"
              idleLabel="Części 2D generowane ręcznie"
            />
            <StatusChip
              active={project.assembly_ready}
              activeLabel={
                project.assembly_pdf_ready
                  ? "Instrukcja PDF gotowa"
                  : "Podgląd montażu gotowy"
              }
              idleLabel="Instrukcja montażu jeszcze nie została wygenerowana"
            />
            <span
              className="rounded-full px-3 py-1"
              style={{
                background: "var(--surface-3)",
                border: "1px solid var(--border)",
                color: "var(--foreground-muted)",
              }}
            >
              {primaryStepPath
                ? `Plik źródłowy: ${primaryStepPath.split("/").at(-1)}`
                : "Brak pliku źródłowego"}
            </span>
          </div>
        </div>
      </section>

      {children}

      <Parts2DSection
        projectName={project.object_name}
        buildApiUrl={buildApiUrl}
        canGenerate={Boolean(project.mesh_url)}
      />

      <AssemblyInstructionsSection
        projectName={project.object_name}
        canGenerate={canGenerateAssembly}
      />
    </div>
  );
}

function MetricCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
      }}
    >
      <p
        className="font-mono text-[10px] uppercase tracking-[0.18em]"
        style={{ color: "var(--foreground-subtle)" }}
      >
        {label}
      </p>
      <p
        className="mt-2 text-2xl font-semibold tracking-tight"
        style={{ color: accent ?? "var(--foreground)" }}
      >
        {value}
      </p>
    </div>
  );
}

function StatusChip({
  active,
  activeLabel,
  idleLabel,
}: {
  active: boolean;
  activeLabel: string;
  idleLabel: string;
}) {
  return (
    <span
      className="rounded-full px-3 py-1"
      style={{
        background: active ? "var(--success-dim)" : "var(--surface-3)",
        border: "1px solid var(--border)",
        color: active ? "var(--success)" : "var(--foreground-muted)",
      }}
    >
      {active ? activeLabel : idleLabel}
    </span>
  );
}
