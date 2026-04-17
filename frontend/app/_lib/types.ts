export type ProjectFile = {
  file_name: string;
  download_url: string;
};

export type ProjectObject = {
  object_name: string;
  files: ProjectFile[];
  primary_step_file?: string | null;
  source_file?: string | null;
  mesh_ready: boolean;
  mesh_url?: string | null;
  parts_2d_ready: boolean;
  parts_2d_url?: string | null;
  assembly_ready: boolean;
  assembly_url?: string | null;
  assembly_pdf_ready: boolean;
  assembly_pdf_url?: string | null;
  assembly_status?: string | null;
  assembly_preview_generated_at?: string | null;
  assembly_full_generated_at?: string | null;
};

export type ProjectsResponse = {
  objects: ProjectObject[];
};

export type Parts2DCategory = "panel" | "connector" | "other";

export type Parts2DGroup = {
  group_id: string;
  category: Parts2DCategory;
  label: string;
  quantity: number;
  dimensions_mm: { length: number; width: number; height: number };
  volume_mm3: number;
  svg_file_name: string;
  svg_url: string;
  part_indexes: number[];
  classification_reason: string;
  grouped: boolean;
};

export type Parts2DPart = {
  part_index: number;
  category: Parts2DCategory;
  group_id: string;
  dimensions_mm: { length: number; width: number; height: number };
  volume_mm3: number;
  classification_reason: string;
};

export type Parts2DManifest = {
  object_name: string;
  source_step_file: string;
  source_step_file_url: string;
  generated_at: string;
  parts_count: number;
  groups_count: number;
  groups: Parts2DGroup[];
  parts: Parts2DPart[];
};

export type MeshPart = {
  part_index: number;
  name: string;
  category: Parts2DCategory;
  dimensions_mm: { length: number; width: number; height: number };
  volume_mm3: number;
  positions: number[];
  normals: number[];
  indices: number[];
};

export type MeshManifest = {
  object_name: string;
  source_step_file: string;
  generated_at: string;
  units: "millimeter";
  meshes: MeshPart[];
};

export type UploadStepResponse = {
  job_id: string;
  object_name: string;
  stream_url: string;
  project_url: string;
  mesh_url: string;
};

export type AssemblyAnalysisResponse = {
  job_id: string;
  object_name: string;
  preview_only: boolean;
  stream_url: string;
  assembly_url: string;
  pdf_url: string;
};

export type JobProgressEvent = {
  job_id: string;
  stage: string;
  progress: number;
  message: string;
  object_name: string;
  project_url?: string;
  mesh_url?: string;
  assembly_url?: string;
  pdf_url?: string;
  preview_only?: boolean;
};

export type UploadProgressEvent = JobProgressEvent;

export type AssemblyPart = {
  part_index: number;
  label: string;
  short_label: string;
  role_name: string;
  category: Parts2DCategory;
  group_id?: string | null;
  group_quantity: number;
  dimensions_mm: { length: number; width: number; height: number };
  volume_mm3: number;
};

export type AssemblyPlanner = {
  source: string;
  model?: string;
  requested_model?: string;
  fallback_model?: string;
  response_id?: string;
  error?: string;
};

export type AssemblyStep = {
  stepNumber: number;
  title: string;
  description: string;
  partIndices: number[];
  contextPartIndices: number[];
  partRoles: Record<string, string>;
  svg_file_name: string;
  svg_url: string;
};

export type AssemblyManifest = {
  object_name: string;
  source_step_file: string;
  generated_at: string;
  preview_only: boolean;
  parts_count: number;
  steps_count: number;
  graph: {
    nodes_count: number;
    edges_count: number;
  };
  planner: AssemblyPlanner;
  preview_svg_url: string;
  preview_png_url: string;
  pdf_url?: string | null;
  parts: AssemblyPart[];
  steps: AssemblyStep[];
};
