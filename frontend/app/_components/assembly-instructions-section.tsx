"use client";

import { useEffect, useMemo, useState } from "react";
import { buildApiUrl, getAssembly, startAssemblyAnalysis } from "@/app/_lib/api";
import type {
  AssemblyAnalysisResponse,
  AssemblyManifest,
  AssemblyStep,
  JobProgressEvent,
} from "@/app/_lib/types";

type AssemblyInstructionsSectionProps = {
  projectName: string;
  canGenerate: boolean;
};

type JobState = {
  response: AssemblyAnalysisResponse;
  progress: JobProgressEvent | null;
};

export default function AssemblyInstructionsSection({
  projectName,
  canGenerate,
}: AssemblyInstructionsSectionProps) {
  const [manifest, setManifest] = useState<AssemblyManifest | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStarting, setIsStarting] = useState(false);
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);

  useEffect(() => {
    let isMounted = true;

    async function loadManifest() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getAssembly(projectName);

        if (!isMounted) {
          return;
        }

        setManifest(data);
        setSelectedStepIndex(0);
      } catch (loadError) {
        if (isMounted) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Nie udało się pobrać instrukcji montażu.",
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadManifest();

    return () => {
      isMounted = false;
    };
  }, [projectName]);

  const selectedStep = useMemo(() => {
    if (!manifest?.steps.length) {
      return null;
    }

    return manifest.steps[selectedStepIndex] ?? manifest.steps[0];
  }, [manifest, selectedStepIndex]);

  async function handleStart(previewOnly: boolean) {
    try {
      setIsStarting(true);
      setError(null);
      const response = await startAssemblyAnalysis(projectName, { previewOnly });
      setJobState({ response, progress: null });

      const eventSource = new EventSource(buildApiUrl(response.stream_url));

      eventSource.addEventListener("progress", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as JobProgressEvent;
        setJobState((current) =>
          current ? { ...current, progress: payload } : current,
        );
      });

      eventSource.addEventListener("completed", async (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as JobProgressEvent;
        setJobState((current) =>
          current ? { ...current, progress: payload } : current,
        );
        eventSource.close();

        try {
          const nextManifest = await getAssembly(projectName);
          setManifest(nextManifest);
          setSelectedStepIndex(0);
        } catch (loadError) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Instrukcja została wygenerowana, ale nie udało się jej odświeżyć.",
          );
        } finally {
          setIsStarting(false);
          setJobState(null);
        }
      });

      eventSource.addEventListener("error", (event) => {
        try {
          const payload = JSON.parse((event as MessageEvent).data) as JobProgressEvent;
          setError(payload.message);
        } catch {
          setError("Analiza montażu zakończyła się błędem.");
        }
        eventSource.close();
        setIsStarting(false);
        setJobState(null);
      });
    } catch (startError) {
      setError(
        startError instanceof Error
          ? startError.message
          : "Nie udało się uruchomić analizy montażu.",
      );
      setIsStarting(false);
      setJobState(null);
    }
  }

  function renderPlannerBadge() {
    if (!manifest) {
      return null;
    }

    const isAi = manifest.planner.source === "ai";
    const label = isAi ? "Plan AI" : manifest.preview_only ? "Tryb preview" : "Fallback deterministyczny";

    return (
      <span
        className="rounded-full px-3 py-1 text-xs font-semibold"
        style={{
          background: isAi ? "rgba(56,189,248,0.14)" : "var(--surface-3)",
          border: "1px solid var(--border)",
          color: isAi ? "#0284c7" : "var(--foreground-muted)",
        }}
      >
        {label}
      </span>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex h-32 items-center justify-center rounded-2xl text-sm"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          color: "var(--foreground-muted)",
        }}
      >
        <span className="animate-pulse">Ładowanie instrukcji montażu...</span>
      </div>
    );
  }

  return (
    <section
      className="rounded-2xl p-6 md:p-8"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p
            className="font-mono text-[10px] uppercase tracking-[0.22em]"
            style={{ color: "var(--foreground-subtle)" }}
          >
            Etap 3
          </p>
          <h2
            className="mt-2 text-xl font-semibold tracking-tight"
            style={{ color: "var(--foreground)" }}
          >
            Instrukcja montażu
          </h2>
          <p
            className="mt-2 max-w-3xl text-sm leading-7"
            style={{ color: "var(--foreground-muted)" }}
          >
            Backend buduje podgląd, graf kontaktów i kolejne kroki. Gdy klucz
            OpenRouter jest dostępny, plan kroków powstaje z pomocą modelu AI;
            w przeciwnym razie system przechodzi na plan deterministyczny.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleStart(true)}
            disabled={isStarting || !canGenerate}
            className="inline-flex h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          >
            Szybki podgląd
          </button>
          <button
            type="button"
            onClick={() => void handleStart(false)}
            disabled={isStarting || !canGenerate}
            className="inline-flex h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--accent)",
              color: "#fff",
            }}
          >
            Pełna instrukcja
          </button>
        </div>
      </div>

      {!canGenerate ? (
        <div
          className="mt-6 rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            color: "var(--foreground-muted)",
          }}
        >
          Najpierw przygotuj model 3D. Backend odtworzy brakujące artefakty
          pomocnicze, ale potrzebuje gotowego mesha z Etapu 1.
        </div>
      ) : null}

      {jobState ? (
        <div
          className="mt-6 rounded-xl p-4"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
          }}
        >
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <p
                className="text-sm font-semibold"
                style={{ color: "var(--foreground)" }}
              >
                {jobState.progress?.message ?? "Uruchamianie analizy montażu..."}
              </p>
              <p
                className="mt-1 text-xs uppercase tracking-[0.18em]"
                style={{ color: "var(--foreground-subtle)" }}
              >
                {jobState.progress?.stage ?? "starting"}
              </p>
            </div>
            <div
              className="rounded-full px-3 py-1 font-mono text-xs"
              style={{
                background: "var(--surface-3)",
                border: "1px solid var(--border)",
                color: "var(--foreground-muted)",
              }}
            >
              {jobState.progress?.progress ?? 0}%
            </div>
          </div>

          <div
            className="mt-4 h-2 overflow-hidden rounded-full"
            style={{ background: "var(--surface-3)" }}
          >
            <div
              className="h-full rounded-full transition-all"
              style={{
                width: `${jobState.progress?.progress ?? 0}%`,
                background: "var(--accent)",
              }}
            />
          </div>
        </div>
      ) : null}

      {error ? (
        <div
          className="mt-6 rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--danger-dim)",
            border: "1px solid rgba(248,113,113,0.25)",
            color: "var(--danger)",
          }}
        >
          {error}
        </div>
      ) : null}

      {manifest ? (
        <div className="mt-8 space-y-6">
          <div className="flex flex-wrap items-center gap-3">
            {renderPlannerBadge()}
            <span
              className="rounded-full px-3 py-1 text-xs font-medium"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--foreground-muted)",
              }}
            >
              Kroki:{" "}
              <span style={{ color: "var(--foreground)" }}>
                {manifest.steps_count}
              </span>
            </span>
            <span
              className="rounded-full px-3 py-1 text-xs font-medium"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--foreground-muted)",
              }}
            >
              Węzły grafu:{" "}
              <span style={{ color: "var(--foreground)" }}>
                {manifest.graph.nodes_count}
              </span>
            </span>
            <span
              className="rounded-full px-3 py-1 text-xs font-medium"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--foreground-muted)",
              }}
            >
              Krawędzie:{" "}
              <span style={{ color: "var(--foreground)" }}>
                {manifest.graph.edges_count}
              </span>
            </span>
            {manifest.planner.model ? (
              <span
                className="rounded-full px-3 py-1 text-xs font-medium"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground-muted)",
                }}
              >
                Model:{" "}
                <span style={{ color: "var(--foreground)" }}>
                  {manifest.planner.model}
                </span>
              </span>
            ) : null}
            {manifest.pdf_url ? (
              <a
                href={buildApiUrl(manifest.pdf_url)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center rounded-full px-4 py-1.5 text-xs font-semibold transition"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground)",
                }}
              >
                Pobierz PDF
              </a>
            ) : null}
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.2fr,0.8fr]">
            <div
              className="overflow-hidden rounded-xl"
              style={{
                background: "#f8fafc",
                border: "1px solid var(--border)",
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={buildApiUrl(manifest.preview_svg_url)}
                alt={`Podgląd projektu ${projectName}`}
                className="h-full w-full object-contain"
              />
            </div>

            <div
              className="rounded-xl p-5"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
              }}
            >
              <p
                className="font-mono text-[10px] uppercase tracking-[0.22em]"
                style={{ color: "var(--foreground-subtle)" }}
              >
                Podsumowanie
              </p>
              <div className="mt-4 space-y-3 text-sm">
                <p style={{ color: "var(--foreground-muted)" }}>
                  Źródło:{" "}
                  <span style={{ color: "var(--foreground)" }}>
                    {manifest.source_step_file}
                  </span>
                </p>
                <p style={{ color: "var(--foreground-muted)" }}>
                  Części:{" "}
                  <span style={{ color: "var(--foreground)" }}>
                    {manifest.parts_count}
                  </span>
                </p>
                <p style={{ color: "var(--foreground-muted)" }}>
                  Wygenerowano:{" "}
                  <span style={{ color: "var(--foreground)" }}>
                    {new Date(manifest.generated_at).toLocaleString("pl-PL")}
                  </span>
                </p>
                {manifest.planner.error ? (
                  <p style={{ color: "var(--danger)" }}>
                    AI fallback: {manifest.planner.error}
                  </p>
                ) : null}
              </div>

              {manifest.preview_only ? (
                <div
                  className="mt-5 rounded-lg px-4 py-3 text-sm"
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    color: "var(--foreground-muted)",
                  }}
                >
                  Podgląd całego mebla jest gotowy. Uruchom pełną instrukcję,
                  aby wygenerować kroki, SVG każdego etapu i PDF.
                </div>
              ) : null}
            </div>
          </div>

          {!manifest.preview_only && selectedStep ? (
            <AssemblyStepViewer
              step={selectedStep}
              totalSteps={manifest.steps.length}
              selectedIndex={selectedStepIndex}
              onSelect={setSelectedStepIndex}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function AssemblyStepViewer({
  step,
  totalSteps,
  selectedIndex,
  onSelect,
}: {
  step: AssemblyStep;
  totalSteps: number;
  selectedIndex: number;
  onSelect: (index: number) => void;
}) {
  return (
    <div
      className="rounded-xl p-5"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
      }}
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p
            className="font-mono text-[10px] uppercase tracking-[0.22em]"
            style={{ color: "var(--foreground-subtle)" }}
          >
            Krok {step.stepNumber}
          </p>
          <h3
            className="mt-2 text-lg font-semibold"
            style={{ color: "var(--foreground)" }}
          >
            {step.title}
          </h3>
          <p
            className="mt-2 max-w-2xl text-sm leading-7"
            style={{ color: "var(--foreground-muted)" }}
          >
            {step.description}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onSelect(Math.max(0, selectedIndex - 1))}
            disabled={selectedIndex === 0}
            className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          >
            Poprzedni
          </button>
          <button
            type="button"
            onClick={() => onSelect(Math.min(totalSteps - 1, selectedIndex + 1))}
            disabled={selectedIndex >= totalSteps - 1}
            className="inline-flex h-10 items-center justify-center rounded-lg px-4 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
            }}
          >
            Następny
          </button>
        </div>
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[1.15fr,0.85fr]">
        <div
          className="overflow-hidden rounded-xl"
          style={{
            background: "#f8fafc",
            border: "1px solid var(--border)",
          }}
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={buildApiUrl(step.svg_url)}
            alt={`Krok ${step.stepNumber}`}
            className="h-full w-full object-contain"
          />
        </div>

        <div className="space-y-4">
          <InfoBlock
            label="Nowe części"
            value={step.partIndices.map((value) => `#${value}`).join(", ")}
          />
          <InfoBlock
            label="Kontekst"
            value={
              step.contextPartIndices.length
                ? step.contextPartIndices.map((value) => `#${value}`).join(", ")
                : "Brak"
            }
          />
          <div
            className="rounded-lg p-4"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
            }}
          >
            <p
              className="text-xs font-semibold uppercase tracking-[0.18em]"
              style={{ color: "var(--foreground-subtle)" }}
            >
              Role części
            </p>
            <div className="mt-3 space-y-2 text-sm">
              {Object.entries(step.partRoles).map(([index, role]) => (
                <div
                  key={index}
                  className="flex items-start justify-between gap-4"
                >
                  <span style={{ color: "var(--foreground)" }}>#{index}</span>
                  <span
                    className="text-right"
                    style={{ color: "var(--foreground-muted)" }}
                  >
                    {role}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function InfoBlock({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-lg p-4"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      <p
        className="text-xs font-semibold uppercase tracking-[0.18em]"
        style={{ color: "var(--foreground-subtle)" }}
      >
        {label}
      </p>
      <p
        className="mt-2 text-sm"
        style={{ color: "var(--foreground)" }}
      >
        {value}
      </p>
    </div>
  );
}
