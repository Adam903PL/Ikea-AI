from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import assembly_processing
from app.assembly_schema import AssemblyPlan, AssemblyStep
from app.step_processing import write_json_file


def box_positions(
    min_x: float,
    min_y: float,
    min_z: float,
    max_x: float,
    max_y: float,
    max_z: float,
) -> list[float]:
    corners = [
        (min_x, min_y, min_z),
        (max_x, min_y, min_z),
        (min_x, max_y, min_z),
        (max_x, max_y, min_z),
        (min_x, min_y, max_z),
        (max_x, min_y, max_z),
        (min_x, max_y, max_z),
        (max_x, max_y, max_z),
    ]
    positions: list[float] = []
    for corner in corners:
        positions.extend(corner)
    return positions


class AssemblyProcessingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.object_dir = Path(self.temp_dir.name) / "Desk"
        (self.object_dir / "meta").mkdir(parents=True, exist_ok=True)
        (self.object_dir / "parts_2d").mkdir(parents=True, exist_ok=True)
        self.step_file_path = self.object_dir / "desk.step"
        self.step_file_path.write_bytes(b"step")

        mesh_manifest = {
            "object_name": "Desk",
            "source_step_file": "desk.step",
            "generated_at": "2026-04-17T08:00:00+00:00",
            "units": "millimeter",
            "meshes": [
                {
                    "part_index": 1,
                    "name": "part-001",
                    "category": "panel",
                    "dimensions_mm": {"length": 1200.0, "width": 600.0, "height": 18.0},
                    "volume_mm3": 12_960_000.0,
                    "positions": box_positions(-600, -300, 720, 600, 300, 738),
                    "normals": [],
                    "indices": [],
                },
                {
                    "part_index": 2,
                    "name": "part-002",
                    "category": "panel",
                    "dimensions_mm": {"length": 720.0, "width": 500.0, "height": 18.0},
                    "volume_mm3": 6_480_000.0,
                    "positions": box_positions(-350, -260, 0, 350, -242, 720),
                    "normals": [],
                    "indices": [],
                },
                {
                    "part_index": 3,
                    "name": "part-003",
                    "category": "connector",
                    "dimensions_mm": {"length": 40.0, "width": 10.0, "height": 10.0},
                    "volume_mm3": 2_100.0,
                    "positions": box_positions(-40, -240, 360, 0, -230, 370),
                    "normals": [],
                    "indices": [],
                },
            ],
        }
        parts_manifest = {
            "object_name": "Desk",
            "source_step_file": "desk.step",
            "source_step_file_url": "/objects/Desk/files/desk.step",
            "generated_at": "2026-04-17T08:00:00+00:00",
            "parts_count": 3,
            "groups_count": 3,
            "groups": [
                {
                    "group_id": "panel-001",
                    "category": "panel",
                    "label": "Panel blatu 1200x600x18 mm",
                    "quantity": 1,
                    "dimensions_mm": {"length": 1200.0, "width": 600.0, "height": 18.0},
                    "volume_mm3": 12_960_000.0,
                    "svg_file_name": "panel-001.svg",
                    "svg_url": "/api/step/parts-2d/Desk/svg/panel-001.svg",
                    "part_indexes": [1],
                    "classification_reason": "panel",
                    "grouped": False,
                },
                {
                    "group_id": "panel-002",
                    "category": "panel",
                    "label": "Panel boku 720x500x18 mm",
                    "quantity": 1,
                    "dimensions_mm": {"length": 720.0, "width": 500.0, "height": 18.0},
                    "volume_mm3": 6_480_000.0,
                    "svg_file_name": "panel-002.svg",
                    "svg_url": "/api/step/parts-2d/Desk/svg/panel-002.svg",
                    "part_indexes": [2],
                    "classification_reason": "panel",
                    "grouped": False,
                },
                {
                    "group_id": "connector-001",
                    "category": "connector",
                    "label": "Konfirmat 40x10x10 mm",
                    "quantity": 1,
                    "dimensions_mm": {"length": 40.0, "width": 10.0, "height": 10.0},
                    "volume_mm3": 2_100.0,
                    "svg_file_name": "connector-001.svg",
                    "svg_url": "/api/step/parts-2d/Desk/svg/connector-001.svg",
                    "part_indexes": [3],
                    "classification_reason": "connector",
                    "grouped": False,
                },
            ],
            "parts": [
                {
                    "part_index": 1,
                    "category": "panel",
                    "group_id": "panel-001",
                    "dimensions_mm": {"length": 1200.0, "width": 600.0, "height": 18.0},
                    "volume_mm3": 12_960_000.0,
                    "classification_reason": "panel",
                },
                {
                    "part_index": 2,
                    "category": "panel",
                    "group_id": "panel-002",
                    "dimensions_mm": {"length": 720.0, "width": 500.0, "height": 18.0},
                    "volume_mm3": 6_480_000.0,
                    "classification_reason": "panel",
                },
                {
                    "part_index": 3,
                    "category": "connector",
                    "group_id": "connector-001",
                    "dimensions_mm": {"length": 40.0, "width": 10.0, "height": 10.0},
                    "volume_mm3": 2_100.0,
                    "classification_reason": "connector",
                },
            ],
        }

        write_json_file(self.object_dir / "meta" / "mesh.json", mesh_manifest)
        write_json_file(self.object_dir / "parts_2d" / "manifest.json", parts_manifest)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_generate_preview_only_manifest_creates_preview_assets(self) -> None:
        manifest = assembly_processing.generate_assembly_manifest(
            "Desk",
            self.object_dir,
            self.step_file_path,
            preview_only=True,
            openrouter_client=None,
        )

        self.assertTrue(manifest["preview_only"])
        self.assertEqual(manifest["steps_count"], 0)
        self.assertTrue((self.object_dir / "assembly" / "preview.svg").is_file())
        self.assertTrue((self.object_dir / "assembly" / "preview.png").is_file())

    def test_generate_full_manifest_falls_back_to_deterministic_planner(self) -> None:
        manifest = assembly_processing.generate_assembly_manifest(
            "Desk",
            self.object_dir,
            self.step_file_path,
            preview_only=False,
            openrouter_client=None,
        )

        self.assertFalse(manifest["preview_only"])
        self.assertEqual(manifest["planner"]["source"], "deterministic")
        self.assertEqual(manifest["steps_count"], 2)
        self.assertTrue((self.object_dir / "assembly" / "steps" / "step-001.svg").is_file())
        self.assertTrue((self.object_dir / "assembly" / "instructions.pdf").is_file())

    def test_normalize_plan_appends_missing_parts(self) -> None:
        parts = assembly_processing._build_part_catalog(
            assembly_processing.load_mesh_manifest(self.object_dir),
            assembly_processing.load_manifest(self.object_dir),
        )
        graph = assembly_processing._build_contact_graph(parts)
        candidate = AssemblyPlan(
            steps=[
                AssemblyStep(
                    stepNumber=1,
                    title="Start",
                    description="Start",
                    partIndices=[1, 2],
                    contextPartIndices=[],
                    partRoles={"1": "panel", "2": "panel"},
                )
            ]
        )

        normalized = assembly_processing._normalize_plan(candidate, parts=parts, contact_graph=graph)

        self.assertEqual(len(normalized), 2)
        self.assertEqual(normalized[-1]["partIndices"], [3])


if __name__ == "__main__":
    unittest.main()
