"use client";

import { useEffect, useState } from "react";
import { generateParts2D, getParts2D } from "@/app/_lib/api";
import type { Parts2DManifest } from "@/app/_lib/types";

type Parts2DSectionProps = {
  projectName: string;
  buildApiUrl: (path: string) => string;
  canGenerate: boolean;
};

export default function Parts2DSection({
  projectName,
  buildApiUrl,
  canGenerate,
}: Parts2DSectionProps) {
  const [manifest, setManifest] = useState<Parts2DManifest | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function loadManifest() {
      try {
        setIsLoading(true);
        setError(null);
        const data = await getParts2D(projectName);

        if (isMounted) {
          setManifest(data);
        }
      } catch (loadError) {
        if (isMounted) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Chwilowy błąd przy pobieraniu sekcji 2D.",
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

  async function handleGenerate() {
    try {
      setIsGenerating(true);
      setError(null);
      const data = await generateParts2D(projectName);
      setManifest(data);
    } catch (generateError) {
      setError(
        generateError instanceof Error
          ? generateError.message
          : "Nie udało się wygenerować części 2D.",
      );
    } finally {
      setIsGenerating(false);
    }
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
        <span className="animate-pulse">Ładowanie analizy części...</span>
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
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <p
            className="font-mono text-[10px] uppercase tracking-[0.22em]"
            style={{ color: "var(--foreground-subtle)" }}
          >
            Analiza komponentów
          </p>
          <h2
            className="mt-2 text-xl font-semibold tracking-tight"
            style={{ color: "var(--foreground)" }}
          >
            Części 2D (rzut izometryczny)
          </h2>
          <p
            className="mt-2 text-sm leading-relaxed"
            style={{ color: "var(--foreground-muted)" }}
          >
            Wyodrębnienie pojedynczych elementów ze złożenia STEP w stylu
            instrukcji IKEA.
          </p>
        </div>

        {!manifest ? (
          <button
            type="button"
            onClick={handleGenerate}
            disabled={isGenerating || !canGenerate}
            className="inline-flex h-11 items-center justify-center rounded-lg px-5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: "var(--accent)",
              color: "#fff",
            }}
          >
            {!canGenerate
              ? "Najpierw przygotuj model 3D"
              : isGenerating
                ? "Trwa analiza..."
                : "Generuj podział części"}
          </button>
        ) : null}
      </div>

      {!manifest && !canGenerate ? (
        <div
          className="mt-6 rounded-xl px-4 py-3 text-sm"
          style={{
            background: "var(--surface-2)",
            border: "1px solid var(--border)",
            color: "var(--foreground-muted)",
          }}
        >
          Generowanie części 2D będzie dostępne po przygotowaniu geometrii 3D
          dla projektu.
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
          <div className="flex flex-wrap gap-4">
            <Chip label="Części ogółem" value={String(manifest.parts_count)} />
            <Chip label="Unikalne grupy" value={String(manifest.groups_count)} />
            <Chip label="Plik źródłowy" value={manifest.source_step_file} />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {manifest.groups.map((group) => {
              const categoryColorMap = {
                panel: "var(--success)",
                connector: "var(--accent)",
                other: "var(--foreground-muted)",
              } as const;
              const color = categoryColorMap[group.category];

              return (
                <div
                  key={group.group_id}
                  className="overflow-hidden rounded-xl transition-all"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                  }}
                  onMouseEnter={(event) => {
                    event.currentTarget.style.borderColor = "var(--border-strong)";
                  }}
                  onMouseLeave={(event) => {
                    event.currentTarget.style.borderColor = "var(--border)";
                  }}
                >
                  <div
                    className="relative flex h-48 items-center justify-center p-4 transition-colors"
                    style={{ background: "#f8fafc" }}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={buildApiUrl(group.svg_url)}
                      alt={group.label}
                      className="h-full w-full object-contain mix-blend-multiply"
                    />
                  </div>
                  <div
                    className="space-y-3 p-4"
                    style={{ borderTop: "1px solid var(--border)" }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p
                        className="font-medium leading-snug"
                        style={{ color: "var(--foreground)" }}
                      >
                        {group.label}
                      </p>
                      <div
                        className="shrink-0 rounded px-2 py-0.5 font-mono text-xs font-bold"
                        style={{
                          background: "var(--surface-3)",
                          color: "var(--foreground)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        ×{group.quantity}
                      </div>
                    </div>

                    <div className="flex items-center justify-between">
                      <span
                        className="rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
                        style={{
                          background: `color-mix(in srgb, ${color} 15%, transparent)`,
                          color,
                          border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`,
                        }}
                      >
                        {group.category}
                      </span>
                      <span
                        className="text-xs"
                        style={{ color: "var(--foreground-subtle)" }}
                      >
                        {(group.volume_mm3 / 1000).toFixed(0)} cm³
                      </span>
                    </div>

                    <div
                      className="text-xs leading-6"
                      style={{ color: "var(--foreground-muted)" }}
                    >
                      <p>
                        Wymiary: {group.dimensions_mm.length} ×{" "}
                        {group.dimensions_mm.width} × {group.dimensions_mm.height} mm
                      </p>
                      <p>{group.classification_reason}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-lg px-4 py-2 text-xs font-medium"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        color: "var(--foreground-muted)",
      }}
    >
      {label}: <span style={{ color: "var(--foreground)" }}>{value}</span>
    </div>
  );
}
