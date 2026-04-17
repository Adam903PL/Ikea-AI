from __future__ import annotations

import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import UploadFile

from app import main


class MainApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.uploads_dir = Path(self.temp_dir.name) / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        main.progress_store.reset()

    def tearDown(self) -> None:
        main.progress_store.reset()
        self.temp_dir.cleanup()

    def test_upload_step_returns_job_descriptor(self) -> None:
        upload_file = UploadFile(
            filename="desk.step",
            file=io.BytesIO(b"step-bytes"),
        )

        with patch.object(main, "UPLOADS_DIR", self.uploads_dir), patch.object(
            main,
            "start_upload_processing_thread",
            lambda **_: None,
        ):
            response = asyncio.run(main.upload_step_file("Desk", upload_file))

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["object_name"], "Desk")
        self.assertIn("job_id", payload)
        self.assertEqual(payload["mesh_url"], "/api/step/mesh/Desk")
        self.assertTrue((self.uploads_dir / "Desk" / "source" / "desk.step").is_file())

    def test_upload_step_rejects_files_over_limit(self) -> None:
        upload_file = UploadFile(
            filename="desk.step",
            file=io.BytesIO(b"12345"),
        )

        with patch.object(main, "UPLOADS_DIR", self.uploads_dir), patch.object(
            main,
            "MAX_UPLOAD_SIZE_BYTES",
            4,
        ):
            with self.assertRaises(main.HTTPException) as context:
                asyncio.run(main.upload_step_file("Desk", upload_file))

        self.assertEqual(context.exception.status_code, 413)
        self.assertEqual(context.exception.detail, "STEP file must not exceed 50 MB.")

    def test_stream_progress_returns_event_stream_response(self) -> None:
        main.progress_store.create_job("job-123", "Desk")
        response = main.stream_progress("job-123")

        self.assertEqual(response.media_type, "text/event-stream")
        self.assertEqual(response.headers["Cache-Control"], "no-cache")

    def test_assembly_analysis_returns_job_descriptor(self) -> None:
        object_dir = self.uploads_dir / "Desk" / "source"
        object_dir.mkdir(parents=True, exist_ok=True)
        (object_dir / "desk.step").write_bytes(b"step-bytes")

        request = main.AssemblyAnalysisRequest(object_name="Desk", preview_only=True)

        with patch.object(main, "UPLOADS_DIR", self.uploads_dir), patch.object(
            main,
            "start_assembly_processing_thread",
            lambda **_: None,
        ):
            response = main.run_assembly_analysis(request)

        payload = json.loads(response.body.decode("utf-8"))
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["object_name"], "Desk")
        self.assertTrue(payload["preview_only"])
        self.assertEqual(payload["assembly_url"], "/api/step/assembly/Desk")


if __name__ == "__main__":
    unittest.main()
