"use client";

import Link from "next/link";
import { startTransition, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  fetchProjects,
  getPrimaryStepPath,
  startStepUpload,
} from "@/app/_lib/api";
import type { ProjectObject, UploadProgressEvent } from "@/app/_lib/types";

type UploadJobState = {
  jobId: string;
  progress: number;
  stage: string;
  message: string;
};

const STAGE_LABELS: Record<string, string> = {
  validating: "Walidacja",
  saving_file: "Zapisywanie pliku",
  loading_step: "Ładowanie modelu",
  extracting_solids: "Wyodrębnianie części",
  triangulating_meshes: "Triangulacja geometrii",
  persisting_artifacts: "Zapisywanie artefaktów",
  completed: "Gotowe",
  failed: "Błąd",
};

export default function ProjectsDashboard() {
  const router = useRouter();
  const eventSourceRef = useRef<EventSource | null>(null);
  const [projects, setProjects] = useState<ProjectObject[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [projectName, setProjectName] = useState("");
  const [projectFile, setProjectFile] = useState<File | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [uploadJob, setUploadJob] = useState<UploadJobState | null>(null);

  async function loadProjects() {
    try {
      setIsLoading(true);
      setError(null);
      const nextProjects = await fetchProjects();
      setProjects(nextProjects);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Wystąpił błąd podczas pobierania projektów.",
      );
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function loadProjectsSafely() {
      try {
        setIsLoading(true);
        setError(null);
        const nextProjects = await fetchProjects();

        if (isMounted) {
          setProjects(nextProjects);
        }
      } catch (loadError) {
        if (isMounted) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Wystąpił błąd podczas pobierania projektów.",
          );
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    void loadProjectsSafely();

    return () => {
      isMounted = false;
      closeUploadStream();
    };
  }, []);

  function closeUploadStream() {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }

  function handleUploadProgress(event: MessageEvent<string>) {
    const payload = parseUploadEvent(event);

    if (!payload) {
      return;
    }

    setUploadJob({
      jobId: payload.job_id,
      progress: payload.progress,
      stage: payload.stage,
      message: payload.message,
    });
  }

  function handleUploadCompleted(event: MessageEvent<string>) {
    const payload = parseUploadEvent(event);

    if (!payload) {
      return;
    }

    setUploadJob({
      jobId: payload.job_id,
      progress: payload.progress,
      stage: payload.stage,
      message: payload.message,
    });
    closeUploadStream();

    const nextProjectPath = `/projects/${encodeURIComponent(payload.object_name)}`;
    setProjectName("");
    setProjectFile(null);

    startTransition(() => {
      router.push(nextProjectPath);
      router.refresh();
    });
  }

  function handleUploadError(event: MessageEvent<string>) {
    const payload = parseUploadEvent(event);

    if (!payload) {
      return;
    }

    setSubmitError(payload.message);
    setUploadJob(null);
    closeUploadStream();
    setIsSubmitting(false);
  }

  function parseUploadEvent(
    event: MessageEvent<string>,
  ): UploadProgressEvent | null {
    if (typeof event.data !== "string" || !event.data) {
      return null;
    }

    try {
      return JSON.parse(event.data) as UploadProgressEvent;
    } catch {
      return null;
    }
  }

  function connectUploadProgressStream(streamUrl: string) {
    closeUploadStream();
    const nextEventSource = new EventSource(streamUrl);
    eventSourceRef.current = nextEventSource;

    nextEventSource.addEventListener("progress", (event) =>
      handleUploadProgress(event as MessageEvent<string>),
    );
    nextEventSource.addEventListener("completed", (event) =>
      handleUploadCompleted(event as MessageEvent<string>),
    );
    nextEventSource.addEventListener("error", (event) =>
      handleUploadError(event as MessageEvent<string>),
    );
    nextEventSource.onerror = () => {
      if (eventSourceRef.current) {
        setSubmitError("Połączenie z kanałem postępu zostało przerwane.");
        setUploadJob(null);
        closeUploadStream();
        setIsSubmitting(false);
      }
    };
  }

  async function handleCreateProject(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!projectName.trim()) {
      setSubmitError("Podaj nazwę projektu.");
      return;
    }

    if (!projectFile) {
      setSubmitError("Dodaj plik STEP lub STP.");
      return;
    }

    try {
      setIsSubmitting(true);
      setSubmitError(null);
      setUploadJob({
        jobId: "pending",
        progress: 5,
        stage: "validating",
        message: "Przygotowuję przesyłanie pliku STEP.",
      });

      const response = await startStepUpload(projectName.trim(), projectFile);
      setUploadJob({
        jobId: response.job_id,
        progress: 12,
        stage: "saving_file",
        message: "Plik został odebrany. Czekam na kolejne etapy przetwarzania.",
      });

      connectUploadProgressStream(response.stream_url);
    } catch (uploadError) {
      setSubmitError(
        uploadError instanceof Error
          ? uploadError.message
          : "Nie udało się utworzyć projektu.",
      );
      setUploadJob(null);
      setIsSubmitting(false);
      closeUploadStream();
    } finally {
      setIsSubmitting(false);
    }
  }

  const isUploadInProgress = isSubmitting || uploadJob !== null;
  const uploadStageLabel = uploadJob ? STAGE_LABELS[uploadJob.stage] : null;

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section
        className="rounded-2xl p-6 md:p-8"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
        }}
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl space-y-4">
            <div
              className="inline-flex rounded-full px-3 py-1 font-mono text-[10px] uppercase tracking-[0.22em]"
              style={{
                background: "var(--accent-dim)",
                border: "1px solid var(--accent-border)",
                color: "var(--accent)",
              }}
            >
              Projekty
            </div>
            <div>
              <h2
                className="text-2xl font-semibold tracking-tight md:text-3xl"
                style={{ color: "var(--foreground)" }}
              >
                Modele 3D gotowe do podglądu i dalszej analizy.
              </h2>
              <p
                className="mt-3 max-w-xl text-sm leading-7 md:text-base"
                style={{ color: "var(--foreground-muted)" }}
              >
                Dodaj plik STEP, uruchom analizę backendową i przejdź od razu do
                projektu z gotową geometrią 3D.
              </p>
              <div
                className="mt-4 flex max-w-xl items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium leading-relaxed"
                style={{
                  background: "var(--danger-dim)",
                  border: "1px solid rgba(248,113,113,0.25)",
                  color: "var(--danger)",
                }}
              >
                <span className="text-sm">Uwaga:</span>
                Analiza plików STEP działa obecnie w środowisku lokalnym z
                backendem FastAPI uruchomionym w Pythonie.
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              setSubmitError(null);
              setUploadJob(null);
              setIsDialogOpen(true);
            }}
            className="inline-flex h-11 items-center justify-center rounded-xl px-5 text-sm font-semibold transition-all"
            style={{
              background: "var(--accent)",
              color: "#fff",
              boxShadow: "0 0 24px rgba(124,92,252,0.35)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.opacity = "0.88";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.opacity = "1";
            }}
          >
            + Nowy projekt
          </button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {isLoading
          ? Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="h-56 animate-pulse rounded-2xl"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                }}
              />
            ))
          : null}

        {!isLoading && error ? (
          <div
            className="col-span-full rounded-2xl p-6 text-sm"
            style={{
              background: "var(--danger-dim)",
              border: "1px solid rgba(248,113,113,0.25)",
              color: "var(--danger)",
            }}
          >
            <p className="font-semibold">Nie udało się pobrać projektów.</p>
            <p className="mt-2" style={{ color: "var(--foreground-muted)" }}>
              {error}
            </p>
            <button
              type="button"
              onClick={() => {
                void loadProjects();
              }}
              className="mt-4 inline-flex h-9 items-center justify-center rounded-lg px-4 text-sm font-medium transition"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--danger)",
              }}
            >
              Odśwież widok
            </button>
          </div>
        ) : null}

        {!isLoading && !error && projects.length === 0 ? (
          <div
            className="col-span-full rounded-2xl p-10 text-center"
            style={{
              background: "var(--surface)",
              border: "1px dashed var(--border-strong)",
            }}
          >
            <p
              className="text-lg font-semibold"
              style={{ color: "var(--foreground)" }}
            >
              Brak projektów
            </p>
            <p className="mt-2 text-sm" style={{ color: "var(--foreground-muted)" }}>
              Dodaj pierwszy plik STEP i zacznij budować bibliotekę modeli.
            </p>
          </div>
        ) : null}

        {!isLoading && !error
          ? projects.map((project) => {
              const primaryStepPath = getPrimaryStepPath(project);

              return (
                <Link
                  key={project.object_name}
                  href={`/projects/${encodeURIComponent(project.object_name)}`}
                  className="group flex min-h-56 flex-col justify-between rounded-2xl p-6 transition-all"
                  style={{
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLAnchorElement).style.borderColor =
                      "var(--border-strong)";
                    (e.currentTarget as HTMLAnchorElement).style.background =
                      "var(--surface-2)";
                    (e.currentTarget as HTMLAnchorElement).style.transform =
                      "translateY(-2px)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLAnchorElement).style.borderColor =
                      "var(--border)";
                    (e.currentTarget as HTMLAnchorElement).style.background =
                      "var(--surface)";
                    (e.currentTarget as HTMLAnchorElement).style.transform =
                      "translateY(0)";
                  }}
                >
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p
                          className="text-xs font-semibold uppercase tracking-[0.22em]"
                          style={{ color: "var(--foreground-subtle)" }}
                        >
                          Projekt
                        </p>
                        <h3
                          className="mt-2 text-xl font-semibold tracking-tight"
                          style={{ color: "var(--foreground)" }}
                        >
                          {project.object_name}
                        </h3>
                      </div>
                      <span
                        className="rounded-full px-3 py-1 text-xs font-medium"
                        style={{
                          background: "var(--surface-3)",
                          color: "var(--foreground-muted)",
                        }}
                      >
                        {project.files.length} plik
                        {project.files.length === 1 ? "" : "i"}
                      </span>
                    </div>

                    <div
                      className="rounded-xl p-4 text-sm"
                      style={{
                        background: "var(--surface-2)",
                        border: "1px solid var(--border)",
                      }}
                    >
                      <p
                        className="font-medium"
                        style={{ color: "var(--foreground-muted)" }}
                      >
                        Główne źródło
                      </p>
                      <p
                        className="mt-1.5 truncate font-mono text-[12px]"
                        style={{ color: "var(--foreground-subtle)" }}
                      >
                        {primaryStepPath
                          ? primaryStepPath.split("/").at(-1)
                          : "Brak pliku głównego"}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-2 text-[11px] font-medium">
                      <span
                        className="rounded-full px-3 py-1"
                        style={{
                          background: project.mesh_ready
                            ? "var(--success-dim)"
                            : "var(--surface-2)",
                          border: "1px solid var(--border)",
                          color: project.mesh_ready
                            ? "var(--success)"
                            : "var(--foreground-muted)",
                        }}
                      >
                        {project.mesh_ready ? "Mesh 3D gotowy" : "Mesh 3D w przygotowaniu"}
                      </span>
                      <span
                        className="rounded-full px-3 py-1"
                        style={{
                          background: project.parts_2d_ready
                            ? "var(--success-dim)"
                            : "var(--surface-2)",
                          border: "1px solid var(--border)",
                          color: project.parts_2d_ready
                            ? "var(--success)"
                            : "var(--foreground-muted)",
                        }}
                      >
                        {project.parts_2d_ready
                          ? "Części 2D gotowe"
                          : "Części 2D na żądanie"}
                      </span>
                    </div>
                  </div>

                  <div
                    className="mt-6 flex items-center justify-between text-sm font-medium"
                    style={{ color: "var(--foreground-muted)" }}
                  >
                    <span>Otwórz projekt</span>
                    <span
                      className="transition-transform group-hover:translate-x-1"
                      style={{ color: "var(--accent)" }}
                    >
                      →
                    </span>
                  </div>
                </Link>
              );
            })
          : null}
      </section>

      {isDialogOpen ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center px-4 py-8"
          style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
        >
          <div
            className="w-full max-w-xl rounded-2xl p-6 md:p-8"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border-strong)",
              boxShadow: "0 40px 120px rgba(0,0,0,0.6)",
            }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p
                  className="font-mono text-[10px] uppercase tracking-[0.22em]"
                  style={{ color: "var(--foreground-subtle)" }}
                >
                  Nowy projekt
                </p>
                <h3
                  className="mt-2 text-xl font-semibold tracking-tight"
                  style={{ color: "var(--foreground)" }}
                >
                  Utwórz projekt z pliku STEP
                </h3>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (!isUploadInProgress) {
                    setIsDialogOpen(false);
                    setUploadJob(null);
                    setSubmitError(null);
                  }
                }}
                disabled={isUploadInProgress}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-sm transition disabled:cursor-not-allowed disabled:opacity-50"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--foreground-muted)",
                }}
              >
                ×
              </button>
            </div>

            <form className="mt-7 space-y-5" onSubmit={handleCreateProject}>
              <label className="block space-y-2">
                <span
                  className="text-sm font-medium"
                  style={{ color: "var(--foreground-muted)" }}
                >
                  Nazwa projektu
                </span>
                <input
                  value={projectName}
                  onChange={(event) => setProjectName(event.target.value)}
                  placeholder="np. Biurko Standard"
                  disabled={isUploadInProgress}
                  className="h-11 w-full rounded-xl px-4 text-sm outline-none transition disabled:cursor-not-allowed disabled:opacity-60"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    color: "var(--foreground)",
                  }}
                  onFocus={(e) => {
                    (e.currentTarget as HTMLInputElement).style.borderColor =
                      "var(--accent-border)";
                  }}
                  onBlur={(e) => {
                    (e.currentTarget as HTMLInputElement).style.borderColor =
                      "var(--border)";
                  }}
                />
              </label>

              <label className="block space-y-2">
                <span
                  className="text-sm font-medium"
                  style={{ color: "var(--foreground-muted)" }}
                >
                  Plik STEP
                </span>
                <div
                  className="rounded-xl p-5"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px dashed var(--border-strong)",
                  }}
                >
                  <input
                    type="file"
                    accept=".step,.stp"
                    disabled={isUploadInProgress}
                    onChange={(event) =>
                      setProjectFile(event.target.files?.[0] ?? null)
                    }
                    className="block w-full cursor-pointer text-sm file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:px-4 file:py-2 file:text-sm file:font-medium file:transition disabled:cursor-not-allowed"
                    style={{
                      color: "var(--foreground-muted)",
                    }}
                  />
                  <p
                    className="mt-3 text-[12px]"
                    style={{ color: "var(--foreground-subtle)" }}
                  >
                    {projectFile
                      ? `Wybrano: ${projectFile.name}`
                      : "Dodaj jeden plik .step lub .stp do 50 MB"}
                  </p>
                </div>
              </label>

              {uploadJob ? (
                <div
                  className="rounded-xl p-4"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span style={{ color: "var(--foreground)" }}>
                      {uploadStageLabel ?? "Przetwarzanie"}
                    </span>
                    <span
                      className="font-mono text-xs"
                      style={{ color: "var(--foreground-muted)" }}
                    >
                      {Math.max(0, Math.min(uploadJob.progress, 100))}%
                    </span>
                  </div>
                  <div
                    className="mt-3 h-2 overflow-hidden rounded-full"
                    style={{ background: "var(--surface-3)" }}
                  >
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${Math.max(8, Math.min(uploadJob.progress, 100))}%`,
                        background: "var(--accent)",
                      }}
                    />
                  </div>
                  <p
                    className="mt-3 text-sm leading-6"
                    style={{ color: "var(--foreground-muted)" }}
                  >
                    {uploadJob.message}
                  </p>
                </div>
              ) : null}

              {submitError ? (
                <div
                  className="rounded-xl px-4 py-3 text-sm"
                  style={{
                    background: "var(--danger-dim)",
                    border: "1px solid rgba(248,113,113,0.25)",
                    color: "var(--danger)",
                  }}
                >
                  {submitError}
                </div>
              ) : null}

              <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={() => {
                    if (!isUploadInProgress) {
                      setIsDialogOpen(false);
                      setUploadJob(null);
                      setSubmitError(null);
                    }
                  }}
                  disabled={isUploadInProgress}
                  className="inline-flex h-11 items-center justify-center rounded-xl px-5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    background: "var(--surface-2)",
                    border: "1px solid var(--border)",
                    color: "var(--foreground-muted)",
                  }}
                >
                  Anuluj
                </button>
                <button
                  type="submit"
                  disabled={isUploadInProgress}
                  className="inline-flex h-11 items-center justify-center rounded-xl px-5 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50"
                  style={{
                    background: "var(--accent)",
                    color: "#fff",
                    boxShadow: "0 0 20px rgba(124,92,252,0.3)",
                  }}
                >
                  {isUploadInProgress ? "Trwa przetwarzanie..." : "Utwórz projekt"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
}
