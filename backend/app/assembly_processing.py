from __future__ import annotations

import json
import math
import shutil
import struct
import zlib
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

try:
    import cairosvg
except Exception as exc:  # pragma: no cover - optional runtime dependency
    cairosvg = None
    CAIROSVG_IMPORT_ERROR = str(exc)
else:  # pragma: no cover - depends on local runtime
    CAIROSVG_IMPORT_ERROR = None

try:
    from reportlab.graphics import renderPDF
    from reportlab.lib.colors import HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from svglib.svglib import svg2rlg
except Exception as exc:  # pragma: no cover - optional runtime dependency
    renderPDF = None
    HexColor = None
    A4 = (595.27, 841.89)
    canvas = None
    svg2rlg = None
    PDF_IMPORT_ERROR = str(exc)
else:  # pragma: no cover - depends on local runtime
    PDF_IMPORT_ERROR = None

from app.assembly_schema import AssemblyPlan, AssemblyStep, parse_assembly_plan
from app.openrouter_client import OpenRouterClient, OpenRouterError
from app.step_processing import (
    compute_file_hash,
    load_manifest,
    load_mesh_manifest,
    load_project_metadata,
    update_project_metadata,
    utc_now_iso,
    write_json_file,
)

ASSEMBLY_DIR_NAME = "assembly"
ASSEMBLY_STEPS_DIR_NAME = "steps"
ASSEMBLY_MANIFEST_FILE_NAME = "manifest.json"
ASSEMBLY_PREVIEW_SVG_NAME = "preview.svg"
ASSEMBLY_PREVIEW_PNG_NAME = "preview.png"
ASSEMBLY_PDF_NAME = "instructions.pdf"

PROJECTION_DIRECTION = (-1.0, -2.0, 0.5)
SVG_CANVAS_WIDTH = 1200
SVG_CANVAS_HEIGHT = 900
SCENE_PADDING = 72
STEP_EXPLODE_DISTANCE_MM = 90.0

CATEGORY_ORDER = {"panel": 0, "other": 1, "connector": 2}
CATEGORY_FILL = {
    "panel": ("#f4f5f7", "#d7dbe1", "#eef1f5"),
    "connector": ("#d6efe8", "#b9e6d7", "#edf8f4"),
    "other": ("#eceff4", "#d9deea", "#f6f7fb"),
}
CONTEXT_FILL = ("#f3f4f6", "#eceef1", "#f8f9fb")
VISIBLE_STROKE = "#20242b"
HIDDEN_STROKE = "#b8bec7"
CONTEXT_STROKE = "#8f96a1"
ARROW_STROKE = "#6d7a8d"
LABEL_FILL = "#20242b"

BOX_EDGES = [
    (0, 1),
    (1, 3),
    (3, 2),
    (2, 0),
    (4, 5),
    (5, 7),
    (7, 6),
    (6, 4),
    (0, 4),
    (1, 5),
    (2, 6),
    (3, 7),
]
VISIBLE_FACES = {
    "left": [0, 2, 6, 4],
    "front": [0, 4, 5, 1],
    "top": [4, 6, 7, 5],
}


def get_assembly_dir(object_dir: Path) -> Path:
    return object_dir / ASSEMBLY_DIR_NAME


def get_assembly_steps_dir(object_dir: Path) -> Path:
    return get_assembly_dir(object_dir) / ASSEMBLY_STEPS_DIR_NAME


def get_assembly_manifest_path(object_dir: Path) -> Path:
    return get_assembly_dir(object_dir) / ASSEMBLY_MANIFEST_FILE_NAME


def get_assembly_preview_svg_path(object_dir: Path) -> Path:
    return get_assembly_dir(object_dir) / ASSEMBLY_PREVIEW_SVG_NAME


def get_assembly_preview_png_path(object_dir: Path) -> Path:
    return get_assembly_dir(object_dir) / ASSEMBLY_PREVIEW_PNG_NAME


def get_assembly_pdf_path(object_dir: Path) -> Path:
    return get_assembly_dir(object_dir) / ASSEMBLY_PDF_NAME


def get_assembly_step_svg_path(object_dir: Path, file_name: str) -> Path:
    return get_assembly_steps_dir(object_dir) / Path(file_name).name


def load_assembly_manifest(object_dir: Path) -> dict[str, Any]:
    manifest_path = get_assembly_manifest_path(object_dir)

    if not manifest_path.is_file():
        raise FileNotFoundError("Assembly manifest has not been generated yet.")

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def generate_assembly_manifest(
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    *,
    preview_only: bool = False,
    force: bool = False,
    progress_callback: Callable[[str, int, str], None] | None = None,
    openrouter_client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    source_hash = compute_file_hash(step_file_path)
    metadata = load_project_metadata(object_dir)
    manifest_path = get_assembly_manifest_path(object_dir)
    preview_svg_path = get_assembly_preview_svg_path(object_dir)
    preview_png_path = get_assembly_preview_png_path(object_dir)
    pdf_path = get_assembly_pdf_path(object_dir)

    cache_valid = (
        manifest_path.is_file()
        and preview_svg_path.is_file()
        and preview_png_path.is_file()
        and metadata.get("assembly_source_hash") == source_hash
        and (
            preview_only
            or (
                pdf_path.is_file()
                and metadata.get("assembly_full_generated_at")
                and metadata.get("assembly_status") == "completed"
            )
        )
    )

    if cache_valid and not force:
        manifest = load_assembly_manifest(object_dir)
        if preview_only or not manifest.get("preview_only", True):
            return manifest

    assembly_dir = get_assembly_dir(object_dir)
    shutil.rmtree(assembly_dir, ignore_errors=True)
    get_assembly_steps_dir(object_dir).mkdir(parents=True, exist_ok=True)

    mesh_manifest = load_mesh_manifest(object_dir)
    parts_manifest = load_manifest(object_dir)
    parts = _build_part_catalog(mesh_manifest, parts_manifest)

    _notify(progress_callback, "building_contact_graph", 18, "Budowanie grafu kontaktow.")
    contact_graph = _build_contact_graph(parts)

    _notify(progress_callback, "rendering_preview", 34, "Renderowanie podgladu mebla.")
    preview_scene = _build_preview_scene(parts)
    _write_scene_svg(
        preview_scene,
        preview_svg_path,
        title=f"Podglad montazu: {object_name}",
        subtitle=f"Plik STEP: {step_file_path.name}",
    )
    _write_scene_png(preview_scene, preview_svg_path, preview_png_path)

    if preview_only:
        generated_at = utc_now_iso()
        manifest = _build_manifest(
            object_name=object_name,
            step_file_path=step_file_path,
            parts=parts,
            contact_graph=contact_graph,
            generated_at=generated_at,
            preview_only=True,
            steps=[],
            planner={"source": "preview"},
        )
        write_json_file(manifest_path, manifest)
        update_project_metadata(
            object_dir,
            object_name=object_name,
            source_file=step_file_path.name,
            source_hash=source_hash,
            assembly_source_hash=source_hash,
            assembly_preview_generated_at=generated_at,
            assembly_full_generated_at=None,
            assembly_status="preview_ready",
        )
        return manifest

    _notify(progress_callback, "calling_ai", 56, "Przygotowanie planu montazu.")
    planner_result = _generate_plan(
        object_name=object_name,
        step_file_path=step_file_path,
        parts=parts,
        contact_graph=contact_graph,
        preview_png_path=preview_png_path,
        openrouter_client=openrouter_client,
    )

    _notify(progress_callback, "validating_plan", 70, "Walidacja i uzupelnianie krokow.")
    normalized_plan = _normalize_plan(
        planner_result["plan"],
        parts=parts,
        contact_graph=contact_graph,
    )

    _notify(progress_callback, "rendering_steps", 82, "Renderowanie kolejnych krokow montazu.")
    rendered_steps = _render_step_svgs(
        object_name=object_name,
        object_dir=object_dir,
        plan=normalized_plan,
        parts=parts,
    )

    _notify(progress_callback, "building_pdf", 95, "Skladanie instrukcji PDF.")
    _write_instruction_pdf(
        object_name=object_name,
        object_dir=object_dir,
        step_file_path=step_file_path,
        steps=rendered_steps,
        planner=planner_result["planner"],
    )

    generated_at = utc_now_iso()
    manifest = _build_manifest(
        object_name=object_name,
        step_file_path=step_file_path,
        parts=parts,
        contact_graph=contact_graph,
        generated_at=generated_at,
        preview_only=False,
        steps=rendered_steps,
        planner=planner_result["planner"],
    )
    write_json_file(manifest_path, manifest)
    update_project_metadata(
        object_dir,
        object_name=object_name,
        source_file=step_file_path.name,
        source_hash=source_hash,
        assembly_source_hash=source_hash,
        assembly_preview_generated_at=generated_at,
        assembly_full_generated_at=generated_at,
        assembly_status="completed",
    )
    return manifest


def _notify(
    callback: Callable[[str, int, str], None] | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    if callback:
        callback(stage, progress, message)


def _build_part_catalog(
    mesh_manifest: dict[str, Any],
    parts_manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    group_by_id = {group["group_id"]: group for group in parts_manifest.get("groups", [])}
    part_metadata = {
        part["part_index"]: part
        for part in parts_manifest.get("parts", [])
    }

    parts: list[dict[str, Any]] = []

    for mesh in mesh_manifest.get("meshes", []):
        bbox = _compute_bounding_box(mesh.get("positions", []))
        meta = part_metadata.get(mesh["part_index"], {})
        group = group_by_id.get(meta.get("group_id"))
        label = group["label"] if group else mesh.get("name") or f"Part {mesh['part_index']}"
        short_label = _build_short_label(label, mesh["part_index"])
        role_name = _build_role_name(mesh, label)
        parts.append(
            {
                "part_index": mesh["part_index"],
                "name": mesh.get("name") or f"part-{mesh['part_index']:03d}",
                "label": label,
                "short_label": short_label,
                "role_name": role_name,
                "category": mesh["category"],
                "group_id": meta.get("group_id"),
                "dimensions_mm": mesh["dimensions_mm"],
                "volume_mm3": mesh["volume_mm3"],
                "bbox": bbox,
                "center": _bbox_center(bbox),
                "group_quantity": group["quantity"] if group else 1,
            }
        )

    parts.sort(
        key=lambda item: (
            CATEGORY_ORDER.get(item["category"], 99),
            -float(item["volume_mm3"]),
            item["part_index"],
        )
    )
    return parts


def _compute_bounding_box(positions: list[float]) -> dict[str, float]:
    if not positions:
        return {
            "min_x": 0.0,
            "max_x": 0.0,
            "min_y": 0.0,
            "max_y": 0.0,
            "min_z": 0.0,
            "max_z": 0.0,
        }

    xs = positions[0::3]
    ys = positions[1::3]
    zs = positions[2::3]
    return {
        "min_x": float(min(xs)),
        "max_x": float(max(xs)),
        "min_y": float(min(ys)),
        "max_y": float(max(ys)),
        "min_z": float(min(zs)),
        "max_z": float(max(zs)),
    }


def _bbox_center(bbox: dict[str, float]) -> tuple[float, float, float]:
    return (
        (bbox["min_x"] + bbox["max_x"]) / 2.0,
        (bbox["min_y"] + bbox["max_y"]) / 2.0,
        (bbox["min_z"] + bbox["max_z"]) / 2.0,
    )


def _build_role_name(mesh: dict[str, Any], label: str) -> str:
    category = mesh["category"]

    if category == "connector":
        return f"lacznik {mesh['part_index']}"

    if category == "panel":
        return label.lower()

    return f"element {mesh['part_index']}"


def _build_short_label(label: str, part_index: int) -> str:
    cleaned = label.replace(" mm", "").strip()
    return f"{cleaned} [{part_index}]"


def _build_contact_graph(parts: list[dict[str, Any]]) -> dict[str, Any]:
    pair_metrics: dict[tuple[int, int], dict[str, Any]] = {}

    for index, left in enumerate(parts):
        for right in parts[index + 1 :]:
            pair_key = tuple(sorted((left["part_index"], right["part_index"])))
            gap = _bbox_gap(left["bbox"], right["bbox"])
            center_distance = _distance(left["center"], right["center"])
            connector_bonus = -18.0 if "connector" in {left["category"], right["category"]} else 0.0
            score = gap + center_distance * 0.08 + connector_bonus
            pair_metrics[pair_key] = {
                "parts": [pair_key[0], pair_key[1]],
                "gap_mm": round(gap, 2),
                "center_distance_mm": round(center_distance, 2),
                "score": round(score, 2),
            }

    selected_edges: set[tuple[int, int]] = set()
    parts_by_index = {part["part_index"]: part for part in parts}

    connectors = [part for part in parts if part["category"] == "connector"]
    non_connectors = [part for part in parts if part["category"] != "connector"]

    for connector in connectors:
        candidates = sorted(
            [
                pair_metrics[tuple(sorted((connector["part_index"], other["part_index"])))]
                for other in non_connectors
                if other["part_index"] != connector["part_index"]
            ],
            key=lambda item: (item["score"], item["center_distance_mm"]),
        )
        for edge in candidates[:2]:
            selected_edges.add(tuple(edge["parts"]))

    for part in non_connectors:
        candidates = sorted(
            [
                pair_metrics[tuple(sorted((part["part_index"], other["part_index"])))]
                for other in parts
                if other["part_index"] != part["part_index"]
            ],
            key=lambda item: (item["score"], item["center_distance_mm"]),
        )
        if candidates:
            selected_edges.add(tuple(candidates[0]["parts"]))

    components = _connected_components(parts, selected_edges)

    while len(components) > 1:
        best_edge: tuple[int, int] | None = None
        best_score: float | None = None

        for left_component in components:
            for right_component in components:
                if left_component is right_component:
                    continue

                for left_index in left_component:
                    for right_index in right_component:
                        edge_key = tuple(sorted((left_index, right_index)))
                        score = pair_metrics[edge_key]["score"]
                        if best_score is None or score < best_score:
                            best_edge = edge_key
                            best_score = score

        if best_edge is None:
            break

        selected_edges.add(best_edge)
        components = _connected_components(parts, selected_edges)

    edges = [
        {
            **pair_metrics[edge_key],
            "labels": [
                parts_by_index[edge_key[0]]["short_label"],
                parts_by_index[edge_key[1]]["short_label"],
            ],
        }
        for edge_key in sorted(selected_edges)
    ]

    adjacency: dict[int, list[int]] = {part["part_index"]: [] for part in parts}
    for edge in edges:
        left, right = edge["parts"]
        adjacency[left].append(right)
        adjacency[right].append(left)

    for neighbors in adjacency.values():
        neighbors.sort()

    return {
        "nodes_count": len(parts),
        "edges_count": len(edges),
        "edges": edges,
        "adjacency": adjacency,
    }


def _connected_components(
    parts: list[dict[str, Any]],
    selected_edges: set[tuple[int, int]],
) -> list[set[int]]:
    adjacency: dict[int, set[int]] = {part["part_index"]: set() for part in parts}

    for left, right in selected_edges:
        adjacency[left].add(right)
        adjacency[right].add(left)

    unvisited = set(adjacency)
    components: list[set[int]] = []

    while unvisited:
        root = unvisited.pop()
        stack = [root]
        component = {root}

        while stack:
            current = stack.pop()
            for neighbor in adjacency[current]:
                if neighbor in unvisited:
                    unvisited.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)

        components.append(component)

    return components


def _bbox_gap(left: dict[str, float], right: dict[str, float]) -> float:
    gap_x = max(0.0, max(right["min_x"] - left["max_x"], left["min_x"] - right["max_x"]))
    gap_y = max(0.0, max(right["min_y"] - left["max_y"], left["min_y"] - right["max_y"]))
    gap_z = max(0.0, max(right["min_z"] - left["max_z"], left["min_z"] - right["max_z"]))
    return math.sqrt(gap_x**2 + gap_y**2 + gap_z**2)


def _distance(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    return math.sqrt(
        (left[0] - right[0]) ** 2
        + (left[1] - right[1]) ** 2
        + (left[2] - right[2]) ** 2
    )


def _build_preview_scene(parts: list[dict[str, Any]]) -> dict[str, Any]:
    descriptors = []

    for part in parts:
        descriptors.append(
            _build_box_descriptor(
                part,
                stroke_color=VISIBLE_STROKE,
                hidden_stroke=HIDDEN_STROKE,
                fill_palette=CATEGORY_FILL.get(part["category"], CATEGORY_FILL["other"]),
                translation=(0.0, 0.0, 0.0),
            )
        )

    return _finalize_scene(
        descriptors,
        title="Podglad calego mebla",
        subtitle="Rzut izometryczny w stylu IKEA",
    )


def _build_box_descriptor(
    part: dict[str, Any],
    *,
    stroke_color: str,
    hidden_stroke: str,
    fill_palette: tuple[str, str, str],
    translation: tuple[float, float, float],
) -> dict[str, Any]:
    corners = _build_box_corners(part["bbox"], translation)
    projected = [_project_point(corner) for corner in corners]
    face_polygons = []

    for face_name, corner_indices in VISIBLE_FACES.items():
        points = [projected[index] for index in corner_indices]
        fill = fill_palette[0]
        if face_name == "front":
            fill = fill_palette[1]
        elif face_name == "top":
            fill = fill_palette[2]
        face_polygons.append({"points": points, "fill": fill})

    visible_edges = _collect_edges(VISIBLE_FACES.values())
    all_edges = {tuple(sorted(edge)) for edge in BOX_EDGES}
    hidden_edges = sorted(all_edges - visible_edges)
    projected_center = _project_point(_translate_point(part["center"], translation))

    return {
        "depth": _depth_value(_translate_point(part["center"], translation)),
        "faces": face_polygons,
        "visible_edges": [
            {"start": projected[left], "end": projected[right], "color": stroke_color}
            for left, right in sorted(visible_edges)
        ],
        "hidden_edges": [
            {"start": projected[left], "end": projected[right], "color": hidden_stroke}
            for left, right in hidden_edges
        ],
        "label": {"text": part["short_label"], "position": projected_center},
    }


def _collect_edges(faces: Any) -> set[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()

    for face in faces:
        for index, current in enumerate(face):
            next_index = face[(index + 1) % len(face)]
            edges.add(tuple(sorted((current, next_index))))

    return edges


def _build_box_corners(
    bbox: dict[str, float],
    translation: tuple[float, float, float],
) -> list[tuple[float, float, float]]:
    min_x = bbox["min_x"] + translation[0]
    max_x = bbox["max_x"] + translation[0]
    min_y = bbox["min_y"] + translation[1]
    max_y = bbox["max_y"] + translation[1]
    min_z = bbox["min_z"] + translation[2]
    max_z = bbox["max_z"] + translation[2]

    return [
        (min_x, min_y, min_z),
        (max_x, min_y, min_z),
        (min_x, max_y, min_z),
        (max_x, max_y, min_z),
        (min_x, min_y, max_z),
        (max_x, min_y, max_z),
        (min_x, max_y, max_z),
        (max_x, max_y, max_z),
    ]


def _project_point(point: tuple[float, float, float]) -> tuple[float, float]:
    view = _normalize(PROJECTION_DIRECTION)
    world_up = (0.0, 0.0, 1.0)
    right = _normalize(_cross(world_up, view))
    up = _normalize(_cross(view, right))
    return (_dot(point, right), _dot(point, up))


def _depth_value(point: tuple[float, float, float]) -> float:
    return _dot(point, _normalize(PROJECTION_DIRECTION))


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _dot(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return left[0] * right[0] + left[1] * right[1] + left[2] * right[2]


def _normalize(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(vector[0] ** 2 + vector[1] ** 2 + vector[2] ** 2) or 1.0
    return (vector[0] / length, vector[1] / length, vector[2] / length)


def _translate_point(
    point: tuple[float, float, float],
    translation: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        point[0] + translation[0],
        point[1] + translation[1],
        point[2] + translation[2],
    )


def _finalize_scene(
    descriptors: list[dict[str, Any]],
    *,
    title: str,
    subtitle: str,
) -> dict[str, Any]:
    descriptors.sort(key=lambda item: item["depth"])

    points: list[tuple[float, float]] = []
    for descriptor in descriptors:
        for face in descriptor["faces"]:
            points.extend(face["points"])
        for edge in descriptor["visible_edges"]:
            points.extend([edge["start"], edge["end"]])
        for edge in descriptor["hidden_edges"]:
            points.extend([edge["start"], edge["end"]])
        points.append(descriptor["label"]["position"])

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)

    width = max(max_x - min_x, 1.0)
    height = max(max_y - min_y, 1.0)
    scale = min(
        (SVG_CANVAS_WIDTH - SCENE_PADDING * 2) / width,
        (SVG_CANVAS_HEIGHT - SCENE_PADDING * 2 - 72) / height,
    )
    offset_x = (SVG_CANVAS_WIDTH - width * scale) / 2.0 - min_x * scale
    offset_y = (SVG_CANVAS_HEIGHT - height * scale) / 2.0 - min_y * scale + 24

    return {
        "width": SVG_CANVAS_WIDTH,
        "height": SVG_CANVAS_HEIGHT,
        "descriptors": descriptors,
        "title": title,
        "subtitle": subtitle,
        "transform": {
            "scale": scale,
            "offset_x": offset_x,
            "offset_y": offset_y,
        },
    }


def _transform_point(point: tuple[float, float], transform: dict[str, float]) -> tuple[float, float]:
    x = point[0] * transform["scale"] + transform["offset_x"]
    y = SVG_CANVAS_HEIGHT - (point[1] * transform["scale"] + transform["offset_y"])
    return (x, y)


def _write_scene_svg(
    scene: dict[str, Any],
    output_path: Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
) -> None:
    transform = scene["transform"]
    svg_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{scene["width"]}" '
            f'height="{scene["height"]}" viewBox="0 0 {scene["width"]} {scene["height"]}">'
        ),
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]

    if title:
        svg_lines.append(
            f'<text x="48" y="52" font-size="24" font-family="Arial, Helvetica, sans-serif" '
            f'font-weight="700" fill="#20242b">{_xml_escape(title)}</text>'
        )
    if subtitle:
        svg_lines.append(
            f'<text x="48" y="82" font-size="13" font-family="Arial, Helvetica, sans-serif" '
            f'fill="#6d7480">{_xml_escape(subtitle)}</text>'
        )

    for descriptor in scene["descriptors"]:
        for face in descriptor["faces"]:
            points = " ".join(
                f"{x:.2f},{y:.2f}"
                for x, y in (_transform_point(point, transform) for point in face["points"])
            )
            svg_lines.append(
                f'<polygon points="{points}" fill="{face["fill"]}" stroke="none"/>'
            )

    for descriptor in scene["descriptors"]:
        for edge in descriptor["hidden_edges"]:
            start = _transform_point(edge["start"], transform)
            end = _transform_point(edge["end"], transform)
            svg_lines.append(
                f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
                f'x2="{end[0]:.2f}" y2="{end[1]:.2f}" '
                f'stroke="{edge["color"]}" stroke-width="1.3" stroke-dasharray="6 5"/>'
            )

        for edge in descriptor["visible_edges"]:
            start = _transform_point(edge["start"], transform)
            end = _transform_point(edge["end"], transform)
            svg_lines.append(
                f'<line x1="{start[0]:.2f}" y1="{start[1]:.2f}" '
                f'x2="{end[0]:.2f}" y2="{end[1]:.2f}" '
                f'stroke="{edge["color"]}" stroke-width="2.2"/>'
            )

        label_position = _transform_point(descriptor["label"]["position"], transform)
        svg_lines.append(
            f'<text x="{label_position[0] + 8:.2f}" y="{label_position[1] - 8:.2f}" '
            f'font-size="12" font-family="Arial, Helvetica, sans-serif" fill="{LABEL_FILL}">'
            f'{_xml_escape(descriptor["label"]["text"])}</text>'
        )

    svg_lines.append("</svg>")
    output_path.write_text("\n".join(svg_lines), encoding="utf-8")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _write_scene_png(scene: dict[str, Any], svg_path: Path, output_path: Path) -> None:
    if cairosvg is not None:
        cairosvg.svg2png(url=str(svg_path), write_to=str(output_path))
        return

    transform = scene["transform"]
    width = int(scene["width"])
    height = int(scene["height"])
    pixels = bytearray([255] * width * height * 3)

    def draw_pixel(x: int, y: int, color: tuple[int, int, int]) -> None:
        if x < 0 or x >= width or y < 0 or y >= height:
            return
        offset = (y * width + x) * 3
        pixels[offset : offset + 3] = bytes(color)

    def draw_line(
        start: tuple[float, float],
        end: tuple[float, float],
        color: tuple[int, int, int],
    ) -> None:
        x1, y1 = int(round(start[0])), int(round(start[1]))
        x2, y2 = int(round(end[0])), int(round(end[1]))
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        step_x = 1 if x1 < x2 else -1
        step_y = 1 if y1 < y2 else -1
        error = dx + dy

        while True:
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    draw_pixel(x1 + offset_x, y1 + offset_y, color)

            if x1 == x2 and y1 == y2:
                break

            twice_error = 2 * error
            if twice_error >= dy:
                error += dy
                x1 += step_x
            if twice_error <= dx:
                error += dx
                y1 += step_y

    for descriptor in scene["descriptors"]:
        for edge in descriptor["hidden_edges"]:
            draw_line(
                _transform_point(edge["start"], transform),
                _transform_point(edge["end"], transform),
                (196, 201, 208),
            )

        for edge in descriptor["visible_edges"]:
            draw_line(
                _transform_point(edge["start"], transform),
                _transform_point(edge["end"], transform),
                (33, 37, 43),
            )

    _write_png(output_path, width, height, pixels)


def _write_png(output_path: Path, width: int, height: int, pixels: bytes) -> None:
    raw_rows = bytearray()

    for row in range(height):
        raw_rows.append(0)
        start = row * width * 3
        end = start + width * 3
        raw_rows.extend(pixels[start:end])

    compressed = zlib.compress(bytes(raw_rows), level=9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack("!I", len(data))
            + tag
            + data
            + struct.pack("!I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png_bytes = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", compressed),
            chunk(b"IEND", b""),
        ]
    )
    output_path.write_bytes(png_bytes)


def _generate_plan(
    *,
    object_name: str,
    step_file_path: Path,
    parts: list[dict[str, Any]],
    contact_graph: dict[str, Any],
    preview_png_path: Path,
    openrouter_client: OpenRouterClient | None,
) -> dict[str, Any]:
    fallback_plan = _build_deterministic_plan(parts, contact_graph)
    planner: dict[str, Any] = {"source": "deterministic"}

    if openrouter_client is None:
        return {"plan": fallback_plan, "planner": planner}

    system_prompt = (
        "Jestes planista instrukcji montazu mebli. "
        "Zwroc wylacznie JSON zgodny ze schematem. "
        "Tytuly i opisy pisz po polsku. "
        "Kazdy krok ma zawierac najwyzej 2 nowe czesci."
    )
    user_prompt = _build_ai_prompt(object_name, step_file_path, parts, contact_graph)

    try:
        ai_payload, ai_meta = openrouter_client.generate_assembly_plan(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            preview_png_path=preview_png_path,
        )
        plan = parse_assembly_plan(ai_payload)
        planner.update(ai_meta)
        return {"plan": plan, "planner": planner}
    except (OpenRouterError, ValueError) as exc:
        planner["error"] = str(exc)
        if openrouter_client.model:
            planner["requested_model"] = openrouter_client.model
        if openrouter_client.fallback_model:
            planner["fallback_model"] = openrouter_client.fallback_model
        return {"plan": fallback_plan, "planner": planner}


def _build_ai_prompt(
    object_name: str,
    step_file_path: Path,
    parts: list[dict[str, Any]],
    contact_graph: dict[str, Any],
) -> str:
    parts_payload = [
        {
            "partIndex": part["part_index"],
            "label": part["label"],
            "shortLabel": part["short_label"],
            "role": part["role_name"],
            "category": part["category"],
            "dimensionsMm": part["dimensions_mm"],
            "centerMm": {
                "x": round(part["center"][0], 2),
                "y": round(part["center"][1], 2),
                "z": round(part["center"][2], 2),
            },
            "groupQuantity": part["group_quantity"],
        }
        for part in parts
    ]

    graph_payload = {
        "edges": contact_graph["edges"],
        "rules": {
            "maxNewPartsPerStep": 2,
            "requireAllPartsExactlyOnceAsNew": True,
            "preferPanelsBeforeConnectors": True,
            "useContextPartsForPreviouslyAssembledGeometry": True,
        },
    }

    return (
        f"Projekt: {object_name}\n"
        f"Plik STEP: {step_file_path.name}\n\n"
        "Zaplanuj instrukcje montazu mebla. "
        "Pierwszy krok moze wprowadzic 1-2 czesci bez kontekstu. "
        "Kazdy kolejny krok musi dodawac 1-2 nowe czesci i moze pokazywac "
        "wczesniej zlozone elementy jako contextPartIndices. "
        "Uwzglednij wszystkie czesci dokladnie raz jako nowe elementy.\n\n"
        f"Czesci:\n{json.dumps(parts_payload, ensure_ascii=False, indent=2)}\n\n"
        f"Graf kontaktow:\n{json.dumps(graph_payload, ensure_ascii=False, indent=2)}"
    )


def _build_deterministic_plan(
    parts: list[dict[str, Any]],
    contact_graph: dict[str, Any],
) -> AssemblyPlan:
    parts_by_index = {part["part_index"]: part for part in parts}
    adjacency = contact_graph["adjacency"]
    structure_parts = [part for part in parts if part["category"] != "connector"]
    connector_parts = [part for part in parts if part["category"] == "connector"]
    steps: list[AssemblyStep] = []
    assembled: set[int] = set()

    if not parts:
        raise ValueError("Assembly planner requires at least one part.")

    if len(structure_parts) >= 2:
        first_indices = [structure_parts[0]["part_index"], structure_parts[1]["part_index"]]
    else:
        first_indices = [parts[0]["part_index"]]

    steps.append(
        AssemblyStep(
            stepNumber=1,
            title=_step_title(parts_by_index, first_indices),
            description=_step_description(parts_by_index, first_indices, []),
            partIndices=first_indices,
            contextPartIndices=[],
            partRoles=_step_roles(parts_by_index, first_indices, []),
        )
    )
    assembled.update(first_indices)

    for part in structure_parts[2:]:
        current_index = part["part_index"]
        context = _nearest_context(current_index, assembled, adjacency, parts_by_index)
        steps.append(
            AssemblyStep(
                stepNumber=len(steps) + 1,
                title=_step_title(parts_by_index, [current_index]),
                description=_step_description(parts_by_index, [current_index], context),
                partIndices=[current_index],
                contextPartIndices=context,
                partRoles=_step_roles(parts_by_index, [current_index], context),
            )
        )
        assembled.add(current_index)

    for part in connector_parts:
        current_index = part["part_index"]
        context = _nearest_context(current_index, assembled, adjacency, parts_by_index, limit=2)
        steps.append(
            AssemblyStep(
                stepNumber=len(steps) + 1,
                title=_step_title(parts_by_index, [current_index]),
                description=_step_description(parts_by_index, [current_index], context),
                partIndices=[current_index],
                contextPartIndices=context,
                partRoles=_step_roles(parts_by_index, [current_index], context),
            )
        )
        assembled.add(current_index)

    return AssemblyPlan(steps=steps)


def _nearest_context(
    part_index: int,
    assembled: set[int],
    adjacency: dict[int, list[int]],
    parts_by_index: dict[int, dict[str, Any]],
    *,
    limit: int = 1,
) -> list[int]:
    direct_neighbors = [neighbor for neighbor in adjacency.get(part_index, []) if neighbor in assembled]

    if direct_neighbors:
        return direct_neighbors[:limit]

    candidates = sorted(
        assembled,
        key=lambda candidate: _distance(
            parts_by_index[part_index]["center"],
            parts_by_index[candidate]["center"],
        ),
    )
    return candidates[:limit]


def _step_title(parts_by_index: dict[int, dict[str, Any]], part_indices: list[int]) -> str:
    if len(part_indices) == 2:
        return (
            f"Polacz {parts_by_index[part_indices[0]]['short_label']} "
            f"z {parts_by_index[part_indices[1]]['short_label']}"
        )

    return f"Dodaj {parts_by_index[part_indices[0]]['short_label']}"


def _step_description(
    parts_by_index: dict[int, dict[str, Any]],
    part_indices: list[int],
    context_indices: list[int],
) -> str:
    part_labels = ", ".join(parts_by_index[index]["short_label"] for index in part_indices)

    if context_indices:
        context_labels = ", ".join(parts_by_index[index]["short_label"] for index in context_indices)
        return f"Polacz {part_labels} z wczesniej zlozonym elementem: {context_labels}."

    if len(part_indices) == 2:
        return f"Rozpocznij montaz od polaczenia czesci {part_labels}."

    return f"Rozpocznij montaz od przygotowania czesci {part_labels}."


def _step_roles(
    parts_by_index: dict[int, dict[str, Any]],
    part_indices: list[int],
    context_indices: list[int],
) -> dict[str, str]:
    indices = part_indices + context_indices
    return {str(index): parts_by_index[index]["role_name"] for index in indices}


def _normalize_plan(
    plan: AssemblyPlan,
    *,
    parts: list[dict[str, Any]],
    contact_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    parts_by_index = {part["part_index"]: part for part in parts}
    valid_indices = set(parts_by_index)
    adjacency = contact_graph["adjacency"]
    steps: list[dict[str, Any]] = []
    seen_new_parts: set[int] = set()

    for candidate in plan.steps:
        new_parts: list[int] = []
        assembled_before = set(seen_new_parts)

        for part_index in candidate.partIndices:
            if part_index in valid_indices and part_index not in seen_new_parts and part_index not in new_parts:
                new_parts.append(part_index)
            if len(new_parts) == 2:
                break

        if not new_parts:
            continue

        context = [
            part_index
            for part_index in candidate.contextPartIndices
            if part_index in assembled_before and part_index not in new_parts
        ]

        if not context and assembled_before:
            context = _nearest_context(
                new_parts[0],
                assembled_before,
                adjacency,
                parts_by_index,
                limit=2,
            )

        step_roles = dict(candidate.partRoles)
        for index in new_parts + context:
            step_roles.setdefault(str(index), parts_by_index[index]["role_name"])

        steps.append(
            {
                "stepNumber": len(steps) + 1,
                "title": candidate.title or _step_title(parts_by_index, new_parts),
                "description": candidate.description
                or _step_description(parts_by_index, new_parts, context),
                "partIndices": new_parts,
                "contextPartIndices": context,
                "partRoles": step_roles,
            }
        )
        seen_new_parts.update(new_parts)

    if seen_new_parts != valid_indices:
        fallback = _build_deterministic_plan(parts, contact_graph)

        for candidate in fallback.steps:
            new_parts = [part_index for part_index in candidate.partIndices if part_index not in seen_new_parts]
            if not new_parts:
                continue

            context = [index for index in candidate.contextPartIndices if index in seen_new_parts]
            steps.append(
                {
                    "stepNumber": len(steps) + 1,
                    "title": _step_title(parts_by_index, new_parts),
                    "description": _step_description(parts_by_index, new_parts, context),
                    "partIndices": new_parts,
                    "contextPartIndices": context,
                    "partRoles": _step_roles(parts_by_index, new_parts, context),
                }
            )
            seen_new_parts.update(new_parts)

    return steps


def _render_step_svgs(
    *,
    object_name: str,
    object_dir: Path,
    plan: list[dict[str, Any]],
    parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    parts_by_index = {part["part_index"]: part for part in parts}
    rendered_steps: list[dict[str, Any]] = []
    assembled_before: set[int] = set()

    for raw_step in plan:
        step_number = raw_step["stepNumber"]
        new_parts = [parts_by_index[index] for index in raw_step["partIndices"]]
        context_indices = sorted(assembled_before)
        context_parts = [parts_by_index[index] for index in context_indices]

        translation = _exploded_translation(new_parts, context_parts or [part for part in parts if part["part_index"] not in raw_step["partIndices"]])
        descriptors = []

        for part in context_parts:
            descriptors.append(
                _build_box_descriptor(
                    part,
                    stroke_color=CONTEXT_STROKE,
                    hidden_stroke="#d3d7de",
                    fill_palette=CONTEXT_FILL,
                    translation=(0.0, 0.0, 0.0),
                )
            )

        for part in new_parts:
            descriptors.append(
                _build_box_descriptor(
                    part,
                    stroke_color=VISIBLE_STROKE,
                    hidden_stroke=HIDDEN_STROKE,
                    fill_palette=CATEGORY_FILL.get(part["category"], CATEGORY_FILL["other"]),
                    translation=translation,
                )
            )

        scene = _finalize_scene(
            descriptors,
            title=f"Krok {step_number}",
            subtitle=raw_step["title"],
        )

        for part in new_parts:
            start = _transform_point(
                _project_point(_translate_point(part["center"], translation)),
                scene["transform"],
            )
            end = _transform_point(_project_point(part["center"]), scene["transform"])
            scene.setdefault("annotations", []).append({"start": start, "end": end})

        file_name = f"step-{step_number:03d}.svg"
        svg_path = get_assembly_step_svg_path(object_dir, file_name)
        _write_scene_svg(
            scene,
            svg_path,
            title=f"Krok {step_number}",
            subtitle=raw_step["description"],
        )

        if scene.get("annotations"):
            _append_scene_annotations(svg_path, scene["annotations"])

        rendered_steps.append(
            {
                **raw_step,
                "svg_file_name": file_name,
                "svg_url": f"/api/step/assembly/{quote(object_name)}/svg/{quote(file_name)}",
            }
        )
        assembled_before.update(raw_step["partIndices"])

    return rendered_steps


def _exploded_translation(
    new_parts: list[dict[str, Any]],
    reference_parts: list[dict[str, Any]],
) -> tuple[float, float, float]:
    new_center = _average_center([part["center"] for part in new_parts])
    reference_center = _average_center([part["center"] for part in reference_parts]) if reference_parts else (0.0, 0.0, 0.0)
    direction = (
        new_center[0] - reference_center[0],
        new_center[1] - reference_center[1],
        new_center[2] - reference_center[2],
    )

    if direction == (0.0, 0.0, 0.0):
        direction = (1.0, -1.0, 0.8)

    normalized = _normalize(direction)
    return (
        normalized[0] * STEP_EXPLODE_DISTANCE_MM,
        normalized[1] * STEP_EXPLODE_DISTANCE_MM,
        normalized[2] * STEP_EXPLODE_DISTANCE_MM * 0.7,
    )


def _average_center(points: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not points:
        return (0.0, 0.0, 0.0)

    total_x = sum(point[0] for point in points)
    total_y = sum(point[1] for point in points)
    total_z = sum(point[2] for point in points)
    count = len(points)
    return (total_x / count, total_y / count, total_z / count)


def _append_scene_annotations(svg_path: Path, annotations: list[dict[str, tuple[float, float]]]) -> None:
    svg_content = svg_path.read_text(encoding="utf-8")
    marker_definition = (
        '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" '
        'orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L9,3 z" '
        f'fill="{ARROW_STROKE}"/></marker></defs>'
    )
    insert_at = svg_content.find(">", svg_content.find("<svg")) + 1
    svg_content = svg_content[:insert_at] + marker_definition + svg_content[insert_at:]

    arrow_lines = []
    for annotation in annotations:
        arrow_lines.append(
            f'<line x1="{annotation["start"][0]:.2f}" y1="{annotation["start"][1]:.2f}" '
            f'x2="{annotation["end"][0]:.2f}" y2="{annotation["end"][1]:.2f}" '
            f'stroke="{ARROW_STROKE}" stroke-width="1.8" marker-end="url(#arrow)"/>'
        )

    svg_content = svg_content.replace("</svg>", "".join(arrow_lines) + "</svg>")
    svg_path.write_text(svg_content, encoding="utf-8")


def _write_instruction_pdf(
    *,
    object_name: str,
    object_dir: Path,
    step_file_path: Path,
    steps: list[dict[str, Any]],
    planner: dict[str, Any],
) -> None:
    pdf_path = get_assembly_pdf_path(object_dir)
    preview_svg_path = get_assembly_preview_svg_path(object_dir)

    if canvas is None or svg2rlg is None or renderPDF is None:
        _write_text_only_pdf(
            pdf_path,
            object_name=object_name,
            step_file_path=step_file_path,
            steps=steps,
            planner=planner,
        )
        return

    document = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4

    document.setTitle(f"Instrukcja montazu - {object_name}")
    document.setFillColor(HexColor("#20242b"))
    document.setFont("Helvetica-Bold", 22)
    document.drawString(48, page_height - 64, f"Instrukcja montazu: {object_name}")
    document.setFont("Helvetica", 12)
    document.setFillColor(HexColor("#5b6470"))
    document.drawString(48, page_height - 92, f"Plik STEP: {step_file_path.name}")
    document.drawString(
        48,
        page_height - 110,
        f"Generator: {planner.get('source', 'deterministic')}",
    )
    _draw_svg_on_pdf(document, preview_svg_path, x=48, y=200, max_width=page_width - 96, max_height=page_height - 250)
    document.showPage()

    for step in steps:
        document.setFillColor(HexColor("#20242b"))
        document.setFont("Helvetica-Bold", 20)
        document.drawString(48, page_height - 64, f"Krok {step['stepNumber']}")
        document.setFont("Helvetica-Bold", 13)
        document.drawString(48, page_height - 90, step["title"])
        document.setFont("Helvetica", 11)
        text_object = document.beginText(48, page_height - 116)
        text_object.setFillColor(HexColor("#5b6470"))
        for line in _wrap_text(step["description"], 92):
            text_object.textLine(line)
        document.drawText(text_object)
        _draw_svg_on_pdf(
            document,
            get_assembly_step_svg_path(object_dir, step["svg_file_name"]),
            x=48,
            y=120,
            max_width=page_width - 96,
            max_height=page_height - 220,
        )
        document.showPage()

    document.save()


def _draw_svg_on_pdf(
    document: Any,
    svg_path: Path,
    *,
    x: float,
    y: float,
    max_width: float,
    max_height: float,
) -> None:
    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        return

    scale = min(max_width / max(drawing.width, 1), max_height / max(drawing.height, 1))
    drawing.width *= scale
    drawing.height *= scale
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, document, x, y)


def _write_text_only_pdf(
    output_path: Path,
    *,
    object_name: str,
    step_file_path: Path,
    steps: list[dict[str, Any]],
    planner: dict[str, Any],
) -> None:
    page_width = 595
    page_height = 842
    pages = [
        [
            ("Helvetica-Bold", 20, 48, 780, f"Instrukcja montazu: {object_name}"),
            ("Helvetica", 12, 48, 754, f"Plik STEP: {step_file_path.name}"),
            ("Helvetica", 12, 48, 736, f"Generator: {planner.get('source', 'deterministic')}"),
            ("Helvetica", 12, 48, 700, "Podglad SVG i kroki sa zapisane obok manifestu assembly."),
        ]
    ]

    for step in steps:
        lines = [
            ("Helvetica-Bold", 18, 48, 780, f"Krok {step['stepNumber']}"),
            ("Helvetica-Bold", 12, 48, 752, step["title"]),
        ]
        y = 726
        for line in _wrap_text(step["description"], 88):
            lines.append(("Helvetica", 11, 48, y, line))
            y -= 18
        lines.append(("Helvetica", 10, 48, y - 8, f"SVG: {step['svg_file_name']}"))
        pages.append(lines)

    _write_minimal_pdf(output_path, pages, page_width=page_width, page_height=page_height)


def _wrap_text(text: str, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def _write_minimal_pdf(
    output_path: Path,
    pages: list[list[tuple[str, int, int, int, str]]],
    *,
    page_width: int,
    page_height: int,
) -> None:
    objects: list[bytes] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    font_object_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_lines in pages:
        content_stream = ["BT"]
        for font_name, font_size, x, y, text in page_lines:
            selected_font = "/F1"
            if font_name == "Helvetica-Bold":
                selected_font = "/F1"
            escaped_text = _escape_pdf_text(text)
            content_stream.append(f"{selected_font} {font_size} Tf {x} {y} Td ({escaped_text}) Tj")
        content_stream.append("ET")
        stream_bytes = "\n".join(content_stream).encode("latin-1", errors="replace")
        content_object_id = add_object(
            b"<< /Length "
            + str(len(stream_bytes)).encode("ascii")
            + b" >>\nstream\n"
            + stream_bytes
            + b"\nendstream"
        )
        content_ids.append(content_object_id)
        page_ids.append(0)

    pages_placeholder_index = len(objects) + 1
    pages_object_id = add_object(b"")

    for index, content_object_id in enumerate(content_ids):
        page_object_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_placeholder_index} 0 R "
                f"/MediaBox [0 0 {page_width} {page_height}] "
                f"/Resources << /Font << /F1 {font_object_id} 0 R >> >> "
                f"/Contents {content_object_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids[index] = page_object_id

    pages_object = (
        f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>"
    ).encode("ascii")
    objects[pages_object_id - 1] = pages_object

    catalog_object_id = add_object(f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>".encode("ascii"))

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_start = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root {catalog_object_id} 0 R >>\n"
            f"startxref\n{xref_start}\n%%EOF"
        ).encode("ascii")
    )
    output_path.write_bytes(bytes(pdf))


def _escape_pdf_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _build_manifest(
    *,
    object_name: str,
    step_file_path: Path,
    parts: list[dict[str, Any]],
    contact_graph: dict[str, Any],
    generated_at: str,
    preview_only: bool,
    steps: list[dict[str, Any]],
    planner: dict[str, Any],
) -> dict[str, Any]:
    return {
        "object_name": object_name,
        "source_step_file": step_file_path.name,
        "generated_at": generated_at,
        "preview_only": preview_only,
        "parts_count": len(parts),
        "steps_count": len(steps),
        "graph": {
            "nodes_count": contact_graph["nodes_count"],
            "edges_count": contact_graph["edges_count"],
        },
        "planner": planner,
        "preview_svg_url": f"/api/step/assembly/{quote(object_name)}/svg/{quote(ASSEMBLY_PREVIEW_SVG_NAME)}",
        "preview_png_url": f"/api/step/assembly/{quote(object_name)}/svg/{quote(ASSEMBLY_PREVIEW_PNG_NAME)}",
        "pdf_url": None if preview_only else f"/api/step/assembly/{quote(object_name)}/pdf",
        "parts": [
            {
                "part_index": part["part_index"],
                "label": part["label"],
                "short_label": part["short_label"],
                "role_name": part["role_name"],
                "category": part["category"],
                "group_id": part["group_id"],
                "group_quantity": part["group_quantity"],
                "dimensions_mm": part["dimensions_mm"],
                "volume_mm3": part["volume_mm3"],
            }
            for part in parts
        ],
        "steps": steps,
    }
