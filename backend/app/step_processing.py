from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

CADQUERY_IMPORT_ERROR: str | None = None

try:
    from cadquery import exporters, importers
except Exception as exc:  # pragma: no cover - depends on local CAD runtime
    exporters = None
    importers = None
    CADQUERY_IMPORT_ERROR = str(exc)


SOURCE_DIR_NAME = "source"
META_DIR_NAME = "meta"
PARTS_2D_DIR_NAME = "parts_2d"
MANIFEST_FILE_NAME = "manifest.json"
MESH_FILE_NAME = "mesh.json"
PROJECT_FILE_NAME = "project.json"

MESH_LINEAR_DEFLECTION_MM = 1.0
MESH_ANGULAR_TOLERANCE = 0.2
GROUPING_TOLERANCE = 0.15
GROUPABLE_MAX_LENGTH_MM = 120.0
PANEL_MIN_LENGTH_MM = 200.0
PANEL_MIN_WIDTH_MM = 120.0
PANEL_MAX_THICKNESS_MM = 40.0
PANEL_MAX_THICKNESS_TO_WIDTH_RATIO = 0.12
CONNECTOR_MAX_LENGTH_MM = 80.0
CONNECTOR_MAX_VOLUME_MM3 = 20_000.0

SVG_EXPORT_OPTIONS = {
    "width": 512,
    "height": 512,
    "marginLeft": 36,
    "marginTop": 36,
    "projectionDir": (-1.0, -2.0, 0.5),
    "showAxes": False,
    "showHidden": True,
    "strokeColor": (28, 28, 28),
    "hiddenColor": (160, 160, 160),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_step_runtime_available() -> None:
    if CADQUERY_IMPORT_ERROR:
        raise RuntimeError(
            "STEP processing is unavailable in the current Python environment. "
            "Run the API with .venv310, because CadQuery/OpenCASCADE is not available here. "
            f"Import error: {CADQUERY_IMPORT_ERROR}"
        )


def get_source_dir(object_dir: Path) -> Path:
    return object_dir / SOURCE_DIR_NAME


def get_meta_dir(object_dir: Path) -> Path:
    return object_dir / META_DIR_NAME


def get_project_metadata_path(object_dir: Path) -> Path:
    return get_meta_dir(object_dir) / PROJECT_FILE_NAME


def get_mesh_path(object_dir: Path) -> Path:
    return get_meta_dir(object_dir) / MESH_FILE_NAME


def get_parts_2d_dir(object_dir: Path) -> Path:
    return object_dir / PARTS_2D_DIR_NAME


def get_parts_2d_manifest_path(object_dir: Path) -> Path:
    return get_parts_2d_dir(object_dir) / MANIFEST_FILE_NAME


def get_parts_2d_svg_path(object_dir: Path, file_name: str) -> Path:
    return get_parts_2d_dir(object_dir) / Path(file_name).name


def compute_file_hash(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as input_file:
        while chunk := input_file.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def load_json_file(json_path: Path) -> dict[str, Any]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def write_json_file(json_path: Path, payload: dict[str, Any]) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_project_metadata(object_dir: Path) -> dict[str, Any]:
    metadata_path = get_project_metadata_path(object_dir)

    if not metadata_path.is_file():
        return {}

    return load_json_file(metadata_path)


def save_project_metadata(
    object_dir: Path,
    *,
    object_name: str,
    source_file: str | None,
    source_hash: str | None,
    mesh_generated_at: str | None = None,
    parts_2d_generated_at: str | None = None,
    assembly_source_hash: str | None = None,
    assembly_preview_generated_at: str | None = None,
    assembly_full_generated_at: str | None = None,
    assembly_status: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "object_name": object_name,
        "source_file": source_file,
        "source_hash": source_hash,
        "mesh_generated_at": mesh_generated_at,
        "parts_2d_generated_at": parts_2d_generated_at,
        "assembly_source_hash": assembly_source_hash,
        "assembly_preview_generated_at": assembly_preview_generated_at,
        "assembly_full_generated_at": assembly_full_generated_at,
        "assembly_status": assembly_status,
        "updated_at": utc_now_iso(),
    }
    write_json_file(get_project_metadata_path(object_dir), metadata)
    return metadata


def update_project_metadata(object_dir: Path, **fields: Any) -> dict[str, Any]:
    metadata = load_project_metadata(object_dir)
    metadata.update(fields)
    metadata["updated_at"] = utc_now_iso()
    write_json_file(get_project_metadata_path(object_dir), metadata)
    return metadata


def load_manifest(object_dir: Path) -> dict[str, Any]:
    manifest_path = get_parts_2d_manifest_path(object_dir)

    if not manifest_path.is_file():
        raise FileNotFoundError("Parts 2D manifest has not been generated yet.")

    return load_json_file(manifest_path)


def load_mesh_manifest(object_dir: Path) -> dict[str, Any]:
    mesh_path = get_mesh_path(object_dir)

    if not mesh_path.is_file():
        raise FileNotFoundError("Mesh artifact has not been generated yet.")

    return load_json_file(mesh_path)


def load_step_workplane(step_file_path: Path):
    ensure_step_runtime_available()
    return importers.importStep(str(step_file_path.resolve()))


def load_step_solids(step_file_path: Path) -> list[Any]:
    workplane = load_step_workplane(step_file_path)
    solids = workplane.solids().vals()

    if not solids:
        raise ValueError("The STEP file does not contain any solids.")

    return solids


def build_mesh_payload(
    object_name: str,
    step_file_path: Path,
    solids: list[Any],
    *,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    parts = [_build_part(index, solid) for index, solid in enumerate(solids, start=1)]
    meshes: list[dict[str, Any]] = []

    total = len(parts)

    for processed_count, part in enumerate(parts, start=1):
        positions, normals, indices = _triangulate_shape(part["shape"])
        meshes.append(
            {
                "part_index": part["part_index"],
                "name": part["representative_key"],
                "category": part["category"],
                "dimensions_mm": part["dimensions_mm"],
                "volume_mm3": part["volume_mm3"],
                "positions": positions,
                "normals": normals,
                "indices": indices,
            }
        )

        if progress_callback:
            progress_callback(processed_count, total, part)

    return {
        "object_name": object_name,
        "source_step_file": step_file_path.name,
        "generated_at": utc_now_iso(),
        "units": "millimeter",
        "meshes": meshes,
    }


def write_mesh_payload(object_dir: Path, payload: dict[str, Any]) -> None:
    write_json_file(get_mesh_path(object_dir), payload)


def ensure_mesh_artifact(
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    *,
    source_hash: str | None = None,
) -> dict[str, Any]:
    mesh_path = get_mesh_path(object_dir)

    if mesh_path.is_file():
        return load_mesh_manifest(object_dir)

    solids = load_step_solids(step_file_path)
    mesh_payload = build_mesh_payload(object_name, step_file_path, solids)
    write_mesh_payload(object_dir, mesh_payload)
    source_hash_value = source_hash or compute_file_hash(step_file_path)
    update_project_metadata(
        object_dir,
        object_name=object_name,
        source_file=step_file_path.name,
        source_hash=source_hash_value,
        mesh_generated_at=mesh_payload["generated_at"],
    )
    return mesh_payload


def generate_parts_2d_manifest(
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    ensure_step_runtime_available()

    source_hash = compute_file_hash(step_file_path)
    metadata = load_project_metadata(object_dir)
    manifest_path = get_parts_2d_manifest_path(object_dir)

    if (
        not force
        and manifest_path.is_file()
        and metadata.get("source_hash") == source_hash
        and metadata.get("parts_2d_generated_at")
    ):
        return load_manifest(object_dir)

    ensure_mesh_artifact(object_name, object_dir, step_file_path, source_hash=source_hash)

    solids = load_step_solids(step_file_path)
    output_dir = get_parts_2d_dir(object_dir)
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    parts = [_build_part(index, solid) for index, solid in enumerate(solids, start=1)]
    groups = _group_parts(parts)
    category_counters = {"panel": 0, "connector": 0, "other": 0}

    for group in groups:
        category = group["category"]
        category_counters[category] += 1
        group["group_id"] = f"{category}-{category_counters[category]:03d}"
        svg_file_name = _build_svg_file_name(group)
        _write_svg(group["representative_shape"], output_dir / svg_file_name)
        group["svg_file_name"] = svg_file_name
        group["svg_url"] = f"/api/step/parts-2d/{quote(object_name)}/svg/{quote(svg_file_name)}"

    parts_payload = [
        {
            "part_index": part["part_index"],
            "category": part["category"],
            "group_id": group["group_id"],
            "dimensions_mm": part["dimensions_mm"],
            "volume_mm3": part["volume_mm3"],
            "classification_reason": part["classification_reason"],
        }
        for group in groups
        for part in group["parts"]
    ]
    parts_payload.sort(key=lambda item: item["part_index"])

    groups_payload = [
        {
            "group_id": group["group_id"],
            "category": group["category"],
            "label": _build_group_label(group),
            "quantity": len(group["parts"]),
            "dimensions_mm": group["representative"]["dimensions_mm"],
            "volume_mm3": group["representative"]["volume_mm3"],
            "svg_file_name": group["svg_file_name"],
            "svg_url": group["svg_url"],
            "part_indexes": [part["part_index"] for part in group["parts"]],
            "classification_reason": group["representative"]["classification_reason"],
            "grouped": len(group["parts"]) > 1,
        }
        for group in groups
    ]

    generated_at = utc_now_iso()
    manifest = {
        "object_name": object_name,
        "source_step_file": step_file_path.name,
        "source_step_file_url": f"/objects/{quote(object_name)}/files/{quote(step_file_path.name)}",
        "generated_at": generated_at,
        "parts_count": len(parts_payload),
        "groups_count": len(groups_payload),
        "groups": groups_payload,
        "parts": parts_payload,
    }

    write_json_file(manifest_path, manifest)
    update_project_metadata(
        object_dir,
        object_name=object_name,
        source_file=step_file_path.name,
        source_hash=source_hash,
        parts_2d_generated_at=generated_at,
    )
    return manifest


def _build_part(part_index: int, solid: Any) -> dict[str, Any]:
    bounding_box = solid.BoundingBox()
    dimensions = sorted([bounding_box.xlen, bounding_box.ylen, bounding_box.zlen], reverse=True)
    rounded_dimensions = _round_dimensions(dimensions)
    volume = round(float(solid.Volume()), 2)
    category, reason = _classify_part(dimensions, volume)

    return {
        "part_index": part_index,
        "category": category,
        "classification_reason": reason,
        "dimensions_mm": {
            "length": rounded_dimensions[0],
            "width": rounded_dimensions[1],
            "height": rounded_dimensions[2],
        },
        "volume_mm3": volume,
        "dimensions_signature": rounded_dimensions,
        "representative_key": f"part-{part_index:03d}",
        "shape": solid,
    }


def _classify_part(dimensions: list[float], volume: float) -> tuple[str, str]:
    length, width, height = dimensions
    height_to_width_ratio = height / max(width, 1.0)

    if (
        length >= PANEL_MIN_LENGTH_MM
        and width >= PANEL_MIN_WIDTH_MM
        and height <= PANEL_MAX_THICKNESS_MM
        and height_to_width_ratio <= PANEL_MAX_THICKNESS_TO_WIDTH_RATIO
    ):
        return "panel", "Large flat solid detected from bounding box proportions."

    if length <= CONNECTOR_MAX_LENGTH_MM and volume <= CONNECTOR_MAX_VOLUME_MM3:
        return "connector", "Small compact solid detected from volume and dimensions."

    return "other", "Solid does not match panel or connector heuristics."


def _group_parts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []

    for part in parts:
        if not _can_group_part(part):
            groups.append(_new_group(part))
            continue

        matching_group = next(
            (
                group
                for group in groups
                if group["category"] == part["category"]
                and group["allow_grouping"]
                and _matches_group(group["representative"], part)
            ),
            None,
        )

        if matching_group:
            matching_group["parts"].append(part)
        else:
            groups.append(_new_group(part))

    groups.sort(
        key=lambda group: (
            {"panel": 0, "connector": 1, "other": 2}[group["category"]],
            -group["representative"]["volume_mm3"],
        )
    )

    return groups


def _new_group(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": part["category"],
        "representative": part,
        "representative_shape": part["shape"],
        "parts": [part],
        "allow_grouping": _can_group_part(part),
    }


def _can_group_part(part: dict[str, Any]) -> bool:
    return (
        part["category"] in {"connector", "other"}
        and part["dimensions_mm"]["length"] <= GROUPABLE_MAX_LENGTH_MM
    )


def _matches_group(left: dict[str, Any], right: dict[str, Any], tolerance: float = GROUPING_TOLERANCE) -> bool:
    if not _within_tolerance(left["volume_mm3"], right["volume_mm3"], tolerance):
        return False

    left_dimensions = left["dimensions_signature"]
    right_dimensions = right["dimensions_signature"]

    return all(
        _within_tolerance(left_dimension, right_dimension, tolerance)
        for left_dimension, right_dimension in zip(left_dimensions, right_dimensions, strict=True)
    )


def _within_tolerance(left: float, right: float, tolerance: float) -> bool:
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) <= scale * tolerance


def _round_dimensions(dimensions: list[float]) -> tuple[float, float, float]:
    return tuple(round(float(value), 2) for value in dimensions)


def _build_svg_file_name(group: dict[str, Any]) -> str:
    label = _build_group_label(group).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", label).strip("-")
    return f"{group['group_id']}-{slug or 'part'}.svg"


def _build_group_label(group: dict[str, Any]) -> str:
    quantity = len(group["parts"])
    category = group["category"]
    dimensions_label = _format_dimensions_label(group["representative"]["dimensions_mm"])

    if category == "panel":
        return f"Panel {dimensions_label} mm"

    if quantity > 1:
        return f"{category.capitalize()} {dimensions_label} mm x{quantity}"

    return f"{category.capitalize()} {dimensions_label} mm"


def _format_dimensions_label(dimensions: dict[str, float]) -> str:
    return "x".join(
        str(int(value)) if float(value).is_integer() else str(value)
        for value in (dimensions["length"], dimensions["width"], dimensions["height"])
    )


def _write_svg(shape: Any, output_path: Path) -> None:
    svg_content = exporters.getSVG(shape, SVG_EXPORT_OPTIONS)
    output_path.write_text(svg_content, encoding="utf-8")


def _triangulate_shape(shape: Any) -> tuple[list[float], list[float], list[int]]:
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    shape.mesh(MESH_LINEAR_DEFLECTION_MM, MESH_ANGULAR_TOLERANCE)
    positions: list[float] = []
    indices: list[int] = []

    for face in shape.Faces():
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face.wrapped, location)

        if triangulation is None:
            continue

        transformation = location.Transformation()
        node_offset = len(positions) // 3

        for node_index in range(1, triangulation.NbNodes() + 1):
            point = triangulation.Node(node_index).Transformed(transformation)
            positions.extend(
                [
                    round(float(point.X()), 4),
                    round(float(point.Y()), 4),
                    round(float(point.Z()), 4),
                ]
            )

        for triangle_index in range(1, triangulation.NbTriangles() + 1):
            first, second, third = triangulation.Triangle(triangle_index).Get()

            if face.wrapped.Orientation() == TopAbs_REVERSED:
                second, third = third, second

            indices.extend(
                [
                    node_offset + first - 1,
                    node_offset + second - 1,
                    node_offset + third - 1,
                ]
            )

    normals = _compute_vertex_normals(positions, indices)
    return positions, normals, indices


def _compute_vertex_normals(positions: list[float], indices: list[int]) -> list[float]:
    normals = [0.0] * len(positions)

    for index in range(0, len(indices), 3):
        first = indices[index] * 3
        second = indices[index + 1] * 3
        third = indices[index + 2] * 3

        ax, ay, az = positions[first : first + 3]
        bx, by, bz = positions[second : second + 3]
        cx, cy, cz = positions[third : third + 3]

        abx, aby, abz = bx - ax, by - ay, bz - az
        acx, acy, acz = cx - ax, cy - ay, cz - az

        nx = aby * acz - abz * acy
        ny = abz * acx - abx * acz
        nz = abx * acy - aby * acx

        for offset in (first, second, third):
            normals[offset] += nx
            normals[offset + 1] += ny
            normals[offset + 2] += nz

    normalized: list[float] = []

    for index in range(0, len(normals), 3):
        nx, ny, nz = normals[index : index + 3]
        length = math.sqrt(nx * nx + ny * ny + nz * nz)

        if length == 0:
            normalized.extend([0.0, 0.0, 1.0])
            continue

        normalized.extend(
            [
                round(nx / length, 6),
                round(ny / length, 6),
                round(nz / length, 6),
            ]
        )

    return normalized
