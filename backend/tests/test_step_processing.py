from __future__ import annotations

import unittest

from app import step_processing


class StepProcessingHeuristicsTests(unittest.TestCase):
    def test_classify_panel_connector_and_other(self) -> None:
        self.assertEqual(
            step_processing._classify_part([300.0, 200.0, 16.0], 120_000.0)[0],
            "panel",
        )
        self.assertEqual(
            step_processing._classify_part([35.0, 8.0, 8.0], 1_800.0)[0],
            "connector",
        )
        self.assertEqual(
            step_processing._classify_part([180.0, 90.0, 60.0], 85_000.0)[0],
            "other",
        )

    def test_matches_group_uses_fifteen_percent_tolerance(self) -> None:
        left = {"volume_mm3": 1000.0, "dimensions_signature": (20.0, 10.0, 10.0)}
        right = {"volume_mm3": 1080.0, "dimensions_signature": (21.0, 9.5, 10.5)}
        wrong = {"volume_mm3": 1500.0, "dimensions_signature": (28.0, 12.0, 8.0)}

        self.assertTrue(step_processing._matches_group(left, right))
        self.assertFalse(step_processing._matches_group(left, wrong))

    def test_grouping_keeps_panels_separate_and_groups_small_connectors(self) -> None:
        connector_a = {
            "part_index": 1,
            "category": "connector",
            "dimensions_mm": {"length": 20.0, "width": 10.0, "height": 10.0},
            "volume_mm3": 1000.0,
            "dimensions_signature": (20.0, 10.0, 10.0),
            "classification_reason": "connector",
            "shape": None,
        }
        connector_b = {
            **connector_a,
            "part_index": 2,
            "volume_mm3": 1040.0,
            "dimensions_signature": (20.5, 10.0, 9.8),
        }
        panel = {
            "part_index": 3,
            "category": "panel",
            "dimensions_mm": {"length": 600.0, "width": 300.0, "height": 18.0},
            "volume_mm3": 3_240_000.0,
            "dimensions_signature": (600.0, 300.0, 18.0),
            "classification_reason": "panel",
            "shape": None,
        }

        groups = step_processing._group_parts([connector_a, connector_b, panel])

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["category"], "panel")
        self.assertEqual(len(groups[1]["parts"]), 2)


if __name__ == "__main__":
    unittest.main()
