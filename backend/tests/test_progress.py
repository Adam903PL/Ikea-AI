from __future__ import annotations

import unittest

from app.progress import JobProgressStore


class JobProgressStoreTests(unittest.TestCase):
    def test_stream_replays_events_until_completion(self) -> None:
        store = JobProgressStore(ttl_seconds=60)
        store.create_job("job-1", "Biurko")
        store.publish(
            "job-1",
            "progress",
            stage="saving_file",
            progress=20,
            message="Zapisywanie pliku.",
            object_name="Biurko",
        )
        store.publish(
            "job-1",
            "completed",
            stage="completed",
            progress=100,
            message="Gotowe.",
            object_name="Biurko",
            mesh_url="/api/step/mesh/Biurko",
        )

        chunks = list(store.stream("job-1", keepalive_seconds=999))
        payload = "".join(chunks)

        self.assertIn("event: progress", payload)
        self.assertIn('"stage": "saving_file"', payload)
        self.assertIn("event: completed", payload)
        self.assertIn('"/api/step/mesh/Biurko"', payload)


if __name__ == "__main__":
    unittest.main()
