import type {
  AssemblyAnalysisResponse,
  AssemblyManifest,
  MeshManifest,
  Parts2DManifest,
  ProjectObject,
  ProjectsResponse,
  UploadStepResponse,
} from "@/app/_lib/types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const API_PROXY_PREFIX = "/api/proxy";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  DEFAULT_API_BASE_URL;

export function buildApiUrl(path: string) {
  if (/^https?:\/\//.test(path)) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  if (typeof window !== "undefined") {
    return `${API_PROXY_PREFIX}${normalizedPath}`;
  }

  return `${API_BASE_URL}${normalizedPath}`;
}

export function getPrimaryStepPath(project: ProjectObject) {
  if (project.primary_step_file) {
    return project.primary_step_file;
  }

  return (
    project.files.find((file) => /\.(step|stp)$/i.test(file.file_name))
      ?.download_url ?? null
  );
}

export async function fetchProjects() {
  const response = await fetch(buildApiUrl("/objects"), {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Nie udało się pobrać listy projektów.");
  }

  const data = (await response.json()) as ProjectsResponse;

  return [...data.objects].sort((first, second) =>
    first.object_name.localeCompare(second.object_name, "pl"),
  );
}

export async function fetchProjectDetails(objectName: string) {
  const response = await fetch(
    buildApiUrl(`/objects/${encodeURIComponent(objectName)}`),
    {
      cache: "no-store",
    },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Nie udało się pobrać danych projektu.");
  }

  return (await response.json()) as ProjectObject;
}

export async function startStepUpload(
  objectName: string,
  file: File,
): Promise<UploadStepResponse> {
  const formData = new FormData();
  formData.append("object_name", objectName.trim());
  formData.append("file", file);

  const response = await fetch(buildApiUrl("/api/step/upload"), {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się przesłać pliku STEP.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as UploadStepResponse;
}

export async function fetchMeshManifest(meshUrl: string): Promise<MeshManifest> {
  const response = await fetch(buildApiUrl(meshUrl), {
    cache: "no-store",
  });

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się pobrać geometrii 3D.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as MeshManifest;
}

export async function generateParts2D(
  objectName: string,
  force = false,
): Promise<Parts2DManifest> {
  const response = await fetch(buildApiUrl("/api/step/parts-2d"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ object_name: objectName, force }),
  });

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się wygenerować podziału na części.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as Parts2DManifest;
}

export async function getParts2D(
  objectName: string,
): Promise<Parts2DManifest | null> {
  const response = await fetch(
    buildApiUrl(`/api/step/parts-2d/${encodeURIComponent(objectName)}`),
    { cache: "no-store" },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się pobrać podziału na części.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as Parts2DManifest;
}

export async function startAssemblyAnalysis(
  objectName: string,
  options: { previewOnly: boolean; force?: boolean },
): Promise<AssemblyAnalysisResponse> {
  const response = await fetch(buildApiUrl("/api/step/assembly-analysis"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      object_name: objectName,
      preview_only: options.previewOnly,
      force: options.force ?? false,
    }),
  });

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się uruchomić analizy montażu.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as AssemblyAnalysisResponse;
}

export async function getAssembly(
  objectName: string,
): Promise<AssemblyManifest | null> {
  const response = await fetch(
    buildApiUrl(`/api/step/assembly/${encodeURIComponent(objectName)}`),
    { cache: "no-store" },
  );

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    const errorMessage = await readErrorMessage(
      response,
      "Nie udało się pobrać instrukcji montażu.",
    );
    throw new Error(errorMessage);
  }

  return (await response.json()) as AssemblyManifest;
}

export async function readErrorMessage(
  response: Response,
  fallbackMessage: string,
): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail || fallbackMessage;
  } catch {
    return fallbackMessage;
  }
}
