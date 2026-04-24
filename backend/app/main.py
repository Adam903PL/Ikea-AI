from __future__ import annotations

import os
import re
import shutil
import threading
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from app.assembly_processing import (
    get_assembly_dir,
    get_assembly_manifest_path,
    get_assembly_pdf_path,
    get_assembly_preview_png_path,
    get_assembly_preview_svg_path,
    get_assembly_step_svg_path,
    load_assembly_manifest,
    generate_assembly_manifest,
)
from app.openrouter_client import OpenRouterClient
from app.progress import progress_store
from app.step_processing import (
    compute_file_hash,
    ensure_mesh_artifact,
    generate_parts_2d_manifest,
    get_mesh_path,
    get_meta_dir,
    get_parts_2d_manifest_path,
    get_parts_2d_svg_path,
    get_source_dir,
    load_manifest,
    load_project_metadata,
    load_step_solids,
    build_mesh_payload,
    save_project_metadata,
    update_project_metadata,
    write_mesh_payload,
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", str(BASE_DIR / "uploads"))).resolve()
ALLOWED_STEP_EXTENSIONS = {".step", ".stp"}
ALLOWED_SVG_EXTENSIONS = {".svg", ".png"}
INVALID_PATH_CHARS = r'[<>:"/\\|?*\x00-\x1F]'
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024

UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="3D Object Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Parts2DRequest(BaseModel):
    object_name: str
    file_name: str | None = None
    force: bool = False


class AssemblyAnalysisRequest(BaseModel):
    object_name: str
    file_name: str | None = None
    preview_only: bool = False
    force: bool = False


def normalize_object_name(object_name: str) -> str:
    cleaned_name = re.sub(r"\s+", " ", object_name).strip()
    cleaned_name = re.sub(INVALID_PATH_CHARS, "_", cleaned_name)
    cleaned_name = cleaned_name.rstrip(". ")

    if cleaned_name in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid object name.")

    return cleaned_name


def normalize_file_name(file_name: str) -> str:
    base_name = Path(file_name).name
    suffix = Path(base_name).suffix.lower()
    stem = re.sub(INVALID_PATH_CHARS, "_", Path(base_name).stem).strip()

    if suffix not in ALLOWED_STEP_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .step and .stp files are supported.")

    if not stem:
        raise HTTPException(status_code=400, detail="Invalid file name.")

    return f"{stem}{suffix}"


def normalize_svg_file_name(file_name: str) -> str:
    base_name = Path(file_name).name
    suffix = Path(base_name).suffix.lower()
    stem = re.sub(INVALID_PATH_CHARS, "_", Path(base_name).stem).strip()

    if suffix not in ALLOWED_SVG_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only .svg and .png files are supported.")

    if not stem:
        raise HTTPException(status_code=400, detail="Invalid file name.")

    return f"{stem}{suffix}"


def ensure_existing_object_dir(object_name: str) -> Path:
    object_dir = UPLOADS_DIR / normalize_object_name(object_name)

    if not object_dir.is_dir():
        raise HTTPException(status_code=404, detail="Object not found.")

    return object_dir


def get_step_search_dirs(object_dir: Path) -> list[Path]:
    source_dir = get_source_dir(object_dir)
    source_files = _list_step_files_in_dir(source_dir) if source_dir.is_dir() else []

    if source_files:
        return [source_dir]

    return [object_dir]


def _list_step_files_in_dir(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []

    return sorted(
        [
            file_path
            for file_path in directory.iterdir()
            if file_path.is_file() and file_path.suffix.lower() in ALLOWED_STEP_EXTENSIONS
        ],
        key=lambda file_path: file_path.name.lower(),
    )


def list_step_files(object_dir: Path) -> list[Path]:
    files: list[Path] = []

    for directory in get_step_search_dirs(object_dir):
        files.extend(_list_step_files_in_dir(directory))

    return files


def resolve_step_file(object_dir: Path, file_name: str | None = None) -> Path:
    search_dirs = get_step_search_dirs(object_dir)

    if file_name:
        normalized_file_name = normalize_file_name(file_name)

        for directory in search_dirs:
            file_path = directory / normalized_file_name

            if file_path.is_file():
                return file_path

        raise HTTPException(status_code=404, detail="STEP file not found.")

    metadata = load_project_metadata(object_dir)
    source_file_name = metadata.get("source_file")

    if source_file_name:
        normalized_file_name = normalize_file_name(source_file_name)

        for directory in search_dirs:
            file_path = directory / normalized_file_name

            if file_path.is_file():
                return file_path

    step_files = list_step_files(object_dir)

    if not step_files:
        raise HTTPException(status_code=404, detail="No STEP file found for this object.")

    return step_files[0]


def get_unique_file_path(target_path: Path) -> Path:
    if not target_path.exists():
        return target_path

    counter = 1

    while True:
        candidate = target_path.with_name(f"{target_path.stem}_{counter}{target_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def build_file_payload(object_name: str, file_path: Path) -> dict[str, str]:
    return {
        "file_name": file_path.name,
        "download_url": f"/objects/{quote(object_name)}/files/{quote(file_path.name)}",
    }


def build_primary_step_url(object_name: str) -> str:
    return f"/objects/{quote(object_name)}/step"


def build_mesh_url(object_name: str) -> str:
    return f"/api/step/mesh/{quote(object_name)}"


def build_parts_2d_url(object_name: str) -> str:
    return f"/api/step/parts-2d/{quote(object_name)}"


def build_assembly_url(object_name: str) -> str:
    return f"/api/step/assembly/{quote(object_name)}"


def build_assembly_pdf_url(object_name: str) -> str:
    return f"/api/step/assembly/{quote(object_name)}/pdf"


def build_project_payload(object_dir: Path) -> dict[str, object]:
    step_files = list_step_files(object_dir)
    file_payload = [build_file_payload(object_dir.name, file_path) for file_path in step_files]
    metadata = load_project_metadata(object_dir)
    primary_step_file = build_primary_step_url(object_dir.name) if file_payload else None
    mesh_ready = get_mesh_path(object_dir).is_file()
    parts_2d_ready = get_parts_2d_manifest_path(object_dir).is_file()
    assembly_manifest_ready = get_assembly_manifest_path(object_dir).is_file()
    assembly_pdf_ready = get_assembly_pdf_path(object_dir).is_file()

    return {
        "object_name": object_dir.name,
        "files": file_payload,
        "primary_step_file": primary_step_file,
        "source_file": metadata.get("source_file"),
        "mesh_ready": mesh_ready,
        "mesh_url": build_mesh_url(object_dir.name) if primary_step_file else None,
        "parts_2d_ready": parts_2d_ready,
        "parts_2d_url": build_parts_2d_url(object_dir.name) if parts_2d_ready else None,
        "assembly_ready": assembly_manifest_ready,
        "assembly_url": build_assembly_url(object_dir.name) if assembly_manifest_ready else None,
        "assembly_pdf_ready": assembly_pdf_ready,
        "assembly_pdf_url": build_assembly_pdf_url(object_dir.name) if assembly_pdf_ready else None,
        "assembly_status": metadata.get("assembly_status"),
        "assembly_preview_generated_at": metadata.get("assembly_preview_generated_at"),
        "assembly_full_generated_at": metadata.get("assembly_full_generated_at"),
    }


def publish_job_progress(
    job_id: str,
    object_name: str,
    *,
    stage: str,
    progress: int,
    message: str,
    event: str = "progress",
    **extra: object,
) -> None:
    progress_store.publish(
        job_id,
        event,
        stage=stage,
        progress=progress,
        message=message,
        object_name=object_name,
        **extra,
    )


def reset_project_artifacts(object_dir: Path) -> None:
    shutil.rmtree(get_source_dir(object_dir), ignore_errors=True)
    shutil.rmtree(get_meta_dir(object_dir), ignore_errors=True)
    shutil.rmtree(object_dir / "parts_2d", ignore_errors=True)
    shutil.rmtree(get_assembly_dir(object_dir), ignore_errors=True)
    object_dir.mkdir(parents=True, exist_ok=True)
    get_source_dir(object_dir).mkdir(parents=True, exist_ok=True)
    get_meta_dir(object_dir).mkdir(parents=True, exist_ok=True)


async def save_upload(uploaded_file: UploadFile, destination: Path) -> int:
    bytes_written = 0

    try:
        with destination.open("wb") as output_file:
            while chunk := await uploaded_file.read(1024 * 1024):
                bytes_written += len(chunk)

                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="STEP file must not exceed 50 MB.")

                output_file.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await uploaded_file.close()

    return bytes_written


def process_uploaded_step(
    *,
    job_id: str,
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    source_hash: str,
) -> None:
    try:
        publish_job_progress(
            job_id,
            object_name,
            stage="loading_step",
            progress=35,
            message="Ładowanie pliku STEP.",
        )
        solids = load_step_solids(step_file_path)

        publish_job_progress(
            job_id,
            object_name,
            stage="extracting_solids",
            progress=50,
            message=f"Wyodrębnianie części ze złożenia ({len(solids)} elementów).",
        )

        def on_mesh_progress(processed_count: int, total: int, part: dict[str, object]) -> None:
            progress = 50 + int((processed_count / max(total, 1)) * 35)
            publish_job_progress(
                job_id,
                object_name,
                stage="triangulating_meshes",
                progress=min(progress, 88),
                message=(
                    f"Triangulacja elementu {processed_count}/{total}: "
                    f"{part['representative_key']}"
                ),
            )

        mesh_payload = build_mesh_payload(
            object_name,
            step_file_path,
            solids,
            progress_callback=on_mesh_progress,
        )

        publish_job_progress(
            job_id,
            object_name,
            stage="persisting_artifacts",
            progress=92,
            message="Zapisywanie geometrii 3D i metadanych projektu.",
        )
        write_mesh_payload(object_dir, mesh_payload)
        update_project_metadata(
            object_dir,
            object_name=object_name,
            source_file=step_file_path.name,
            source_hash=source_hash,
            mesh_generated_at=mesh_payload["generated_at"],
            parts_2d_generated_at=None,
            assembly_source_hash=None,
            assembly_preview_generated_at=None,
            assembly_full_generated_at=None,
            assembly_status=None,
        )

        publish_job_progress(
            job_id,
            object_name,
            event="completed",
            stage="completed",
            progress=100,
            message="Model 3D jest gotowy.",
            project_url=f"/objects/{quote(object_name)}",
            mesh_url=build_mesh_url(object_name),
        )
    except RuntimeError as exc:
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc),
        )
    except ValueError as exc:
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc),
        )
    except Exception as exc:  # pragma: no cover - unexpected runtime failures
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=f"Unexpected processing error: {exc}",
        )


def start_upload_processing_thread(
    *,
    job_id: str,
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    source_hash: str,
) -> None:
    thread = threading.Thread(
        target=process_uploaded_step,
        kwargs={
            "job_id": job_id,
            "object_name": object_name,
            "object_dir": object_dir,
            "step_file_path": step_file_path,
            "source_hash": source_hash,
        },
        daemon=True,
    )
    thread.start()


def process_assembly_analysis(
    *,
    job_id: str,
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    preview_only: bool,
    force: bool,
) -> None:
    try:
        publish_job_progress(
            job_id,
            object_name,
            stage="building_contact_graph",
            progress=8,
            message="Przygotowanie danych montazu.",
        )
        ensure_mesh_artifact(object_name, object_dir, step_file_path)
        generate_parts_2d_manifest(object_name, object_dir, step_file_path, force=force)
        openrouter_client = OpenRouterClient()

        def on_progress(stage: str, progress: int, message: str) -> None:
            publish_job_progress(
                job_id,
                object_name,
                stage=stage,
                progress=progress,
                message=message,
            )

        manifest = generate_assembly_manifest(
            object_name,
            object_dir,
            step_file_path,
            preview_only=preview_only,
            force=force,
            progress_callback=on_progress,
            openrouter_client=openrouter_client,
        )
        publish_job_progress(
            job_id,
            object_name,
            event="completed",
            stage="completed",
            progress=100,
            message="Instrukcja montazu jest gotowa." if not preview_only else "Podglad montazu jest gotowy.",
            assembly_url=build_assembly_url(object_name),
            pdf_url=manifest.get("pdf_url"),
            preview_only=preview_only,
        )
    except RuntimeError as exc:
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc),
        )
    except ValueError as exc:
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc),
        )
    except FileNotFoundError as exc:
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc),
        )
    except Exception as exc:  # pragma: no cover - unexpected runtime failures
        publish_job_progress(
            job_id,
            object_name,
            event="error",
            stage="failed",
            progress=100,
            message=f"Unexpected assembly error: {exc}",
        )


def start_assembly_processing_thread(
    *,
    job_id: str,
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    preview_only: bool,
    force: bool,
) -> None:
    thread = threading.Thread(
        target=process_assembly_analysis,
        kwargs={
            "job_id": job_id,
            "object_name": object_name,
            "object_dir": object_dir,
            "step_file_path": step_file_path,
            "preview_only": preview_only,
            "force": force,
        },
        daemon=True,
    )
    thread.start()


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "3D object backend is running."}


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/objects/upload")
async def upload_objects(
    object_name: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict[str, object]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    normalized_object_name = normalize_object_name(object_name)
    object_dir = UPLOADS_DIR / normalized_object_name
    reset_project_artifacts(object_dir)
    source_dir = get_source_dir(object_dir)

    saved_files: list[dict[str, str]] = []
    primary_file_name: str | None = None
    primary_hash: str | None = None

    for index, uploaded_file in enumerate(files):
        if not uploaded_file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file is missing a name.")

        normalized_file_name = normalize_file_name(uploaded_file.filename)
        destination = get_unique_file_path(source_dir / normalized_file_name)
        await save_upload(uploaded_file, destination)
        saved_files.append(build_file_payload(normalized_object_name, destination))

        if index == 0:
            primary_file_name = destination.name
            primary_hash = compute_file_hash(destination)

    save_project_metadata(
        object_dir,
        object_name=normalized_object_name,
        source_file=primary_file_name,
        source_hash=primary_hash,
        mesh_generated_at=None,
        parts_2d_generated_at=None,
        assembly_source_hash=None,
        assembly_preview_generated_at=None,
        assembly_full_generated_at=None,
        assembly_status=None,
    )

    return {
        "object_name": normalized_object_name,
        "object_folder": f"uploads/{normalized_object_name}",
        "files": saved_files,
        "primary_step_file": build_primary_step_url(normalized_object_name),
    }


@app.post("/api/step/upload")
async def upload_step_file(
    object_name: str = Form(...),
    file: UploadFile = File(...),
) -> JSONResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file is missing a name.")

    normalized_object_name = normalize_object_name(object_name)
    normalized_file_name = normalize_file_name(file.filename)
    object_dir = UPLOADS_DIR / normalized_object_name
    job_id = str(uuid4())

    progress_store.create_job(job_id, normalized_object_name)
    publish_job_progress(
        job_id,
        normalized_object_name,
        stage="validating",
        progress=5,
        message="Walidacja nazwy projektu i pliku STEP.",
    )

    reset_project_artifacts(object_dir)
    destination = get_source_dir(object_dir) / normalized_file_name

    publish_job_progress(
        job_id,
        normalized_object_name,
        stage="saving_file",
        progress=18,
        message="Zapisywanie przesłanego pliku STEP.",
    )

    try:
        await save_upload(file, destination)
    except HTTPException as exc:
        publish_job_progress(
            job_id,
            normalized_object_name,
            event="error",
            stage="failed",
            progress=100,
            message=str(exc.detail),
        )
        raise

    source_hash = compute_file_hash(destination)
    save_project_metadata(
        object_dir,
        object_name=normalized_object_name,
        source_file=destination.name,
        source_hash=source_hash,
        mesh_generated_at=None,
        parts_2d_generated_at=None,
        assembly_source_hash=None,
        assembly_preview_generated_at=None,
        assembly_full_generated_at=None,
        assembly_status=None,
    )

    publish_job_progress(
        job_id,
        normalized_object_name,
        stage="saving_file",
        progress=28,
        message="Plik zapisany. Rozpoczynam analizę modelu 3D.",
    )

    start_upload_processing_thread(
        job_id=job_id,
        object_name=normalized_object_name,
        object_dir=object_dir,
        step_file_path=destination,
        source_hash=source_hash,
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "object_name": normalized_object_name,
            "stream_url": f"/api/progress/{job_id}/stream",
            "project_url": f"/objects/{quote(normalized_object_name)}",
            "mesh_url": build_mesh_url(normalized_object_name),
        },
    )


@app.post("/api/step/assembly-analysis")
def run_assembly_analysis(request: AssemblyAnalysisRequest) -> JSONResponse:
    normalized_object_name = normalize_object_name(request.object_name)
    object_dir = ensure_existing_object_dir(normalized_object_name)
    step_file_path = resolve_step_file(object_dir, request.file_name)
    job_id = str(uuid4())

    progress_store.create_job(job_id, normalized_object_name)
    publish_job_progress(
        job_id,
        normalized_object_name,
        stage="building_contact_graph",
        progress=3,
        message="Uruchamianie analizy montazu.",
    )

    start_assembly_processing_thread(
        job_id=job_id,
        object_name=normalized_object_name,
        object_dir=object_dir,
        step_file_path=step_file_path,
        preview_only=request.preview_only,
        force=request.force,
    )

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "object_name": normalized_object_name,
            "preview_only": request.preview_only,
            "stream_url": f"/api/progress/{job_id}/stream",
            "assembly_url": build_assembly_url(normalized_object_name),
            "pdf_url": build_assembly_pdf_url(normalized_object_name),
        },
    )


@app.get("/api/progress/{job_id}/stream")
def stream_progress(job_id: str) -> StreamingResponse:
    if progress_store.get_record(job_id) is None:
        raise HTTPException(status_code=404, detail="Processing job not found.")

    return StreamingResponse(
        progress_store.stream(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/objects")
def list_objects() -> dict[str, list[dict[str, object]]]:
    objects = [
        build_project_payload(object_dir)
        for object_dir in sorted(
            [directory for directory in UPLOADS_DIR.iterdir() if directory.is_dir()],
            key=lambda directory: directory.name.lower(),
        )
    ]

    return {"objects": objects}


@app.get("/objects/{object_name}")
def get_object(object_name: str) -> dict[str, object]:
    object_dir = ensure_existing_object_dir(object_name)

    if not list_step_files(object_dir):
        raise HTTPException(status_code=404, detail="No STEP file found for this object.")

    return build_project_payload(object_dir)


@app.get("/objects/{object_name}/step")
def get_primary_step_file(object_name: str) -> FileResponse:
    object_dir = ensure_existing_object_dir(object_name)
    return FileResponse(resolve_step_file(object_dir), media_type="application/octet-stream")


@app.get("/objects/{object_name}/files/{file_name}")
def get_step_file(object_name: str, file_name: str) -> FileResponse:
    object_dir = ensure_existing_object_dir(object_name)
    file_path = resolve_step_file(object_dir, file_name)
    return FileResponse(file_path, media_type="application/octet-stream")


@app.get("/api/step/mesh/{object_name}")
def get_mesh(object_name: str) -> dict[str, object]:
    object_dir = ensure_existing_object_dir(object_name)
    step_file_path = resolve_step_file(object_dir)

    try:
        return ensure_mesh_artifact(object_dir.name, object_dir, step_file_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/step/parts-2d")
def generate_parts_2d(request: Parts2DRequest) -> dict[str, object]:
    object_dir = ensure_existing_object_dir(request.object_name)
    step_file_path = resolve_step_file(object_dir, request.file_name)

    try:
        return generate_parts_2d_manifest(
            object_dir.name,
            object_dir,
            step_file_path,
            force=request.force,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/step/parts-2d/{object_name}")
def get_parts_2d(object_name: str) -> dict[str, object]:
    object_dir = ensure_existing_object_dir(object_name)
    manifest_path = get_parts_2d_manifest_path(object_dir)

    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Parts 2D manifest has not been generated yet.")

    return load_manifest(object_dir)


@app.get("/api/step/parts-2d/{object_name}/svg/{file_name}")
def get_parts_2d_svg(object_name: str, file_name: str) -> FileResponse:
    object_dir = ensure_existing_object_dir(object_name)
    normalized_file_name = normalize_svg_file_name(file_name)
    file_path = get_parts_2d_svg_path(object_dir, normalized_file_name)

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="SVG file not found.")

    return FileResponse(file_path, media_type="image/svg+xml")


@app.get("/api/step/assembly/{object_name}")
def get_assembly(object_name: str) -> dict[str, object]:
    object_dir = ensure_existing_object_dir(object_name)

    try:
        return load_assembly_manifest(object_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/step/assembly/{object_name}/svg/{file_name}")
def get_assembly_svg(object_name: str, file_name: str) -> FileResponse:
    object_dir = ensure_existing_object_dir(object_name)
    normalized_file_name = normalize_svg_file_name(file_name)

    if normalized_file_name == get_assembly_preview_svg_path(object_dir).name:
        file_path = get_assembly_preview_svg_path(object_dir)
        media_type = "image/svg+xml"
    elif normalized_file_name == get_assembly_preview_png_path(object_dir).name:
        file_path = get_assembly_preview_png_path(object_dir)
        media_type = "image/png"
    else:
        file_path = get_assembly_step_svg_path(object_dir, normalized_file_name)
        media_type = "image/svg+xml"

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Assembly asset not found.")

    return FileResponse(file_path, media_type=media_type)


@app.get("/api/step/assembly/{object_name}/pdf")
def get_assembly_pdf(object_name: str) -> FileResponse:
    object_dir = ensure_existing_object_dir(object_name)
    pdf_path = get_assembly_pdf_path(object_dir)

    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="Assembly PDF has not been generated yet.")

    return FileResponse(pdf_path, media_type="application/pdf")
