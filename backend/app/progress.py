from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProgressEvent:
    event: str
    data: dict[str, Any]
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class JobRecord:
    job_id: str
    object_name: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    events: list[ProgressEvent] = field(default_factory=list)
    terminal: bool = False


def format_sse_message(event: ProgressEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


class JobProgressStore:
    def __init__(self, ttl_seconds: int = 60 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def cleanup(self) -> None:
        now = time.time()

        with self._lock:
            expired_job_ids = [
                job_id
                for job_id, job in self._jobs.items()
                if now - job.updated_at > self.ttl_seconds
            ]

            for job_id in expired_job_ids:
                self._jobs.pop(job_id, None)

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()

    def create_job(self, job_id: str, object_name: str) -> None:
        self.cleanup()

        with self._lock:
            self._jobs[job_id] = JobRecord(job_id=job_id, object_name=object_name)

    def publish(
        self,
        job_id: str,
        event: str,
        *,
        stage: str,
        progress: int,
        message: str,
        object_name: str,
        **extra: Any,
    ) -> None:
        self.cleanup()
        payload = {
            "job_id": job_id,
            "stage": stage,
            "progress": progress,
            "message": message,
            "object_name": object_name,
            **extra,
        }

        with self._lock:
            job = self._jobs.get(job_id)

            if job is None:
                job = JobRecord(job_id=job_id, object_name=object_name)
                self._jobs[job_id] = job

            job.events.append(ProgressEvent(event=event, data=payload))
            job.updated_at = time.time()
            job.terminal = event in {"completed", "error"}

    def get_record(self, job_id: str) -> JobRecord | None:
        self.cleanup()

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None

            return JobRecord(
                job_id=job.job_id,
                object_name=job.object_name,
                created_at=job.created_at,
                updated_at=job.updated_at,
                events=list(job.events),
                terminal=job.terminal,
            )

    def stream(self, job_id: str, *, keepalive_seconds: float = 15.0):
        last_index = 0
        last_keepalive = time.time()

        while True:
            record = self.get_record(job_id)

            if record is None:
                yield format_sse_message(
                    ProgressEvent(
                        event="error",
                        data={
                            "job_id": job_id,
                            "stage": "failed",
                            "progress": 100,
                            "message": "Nie znaleziono zadania przetwarzania.",
                            "object_name": "",
                        },
                    )
                )
                break

            pending_events = record.events[last_index:]

            if pending_events:
                for event in pending_events:
                    yield format_sse_message(event)
                last_index += len(pending_events)
                last_keepalive = time.time()

            if record.terminal and last_index >= len(record.events):
                break

            if time.time() - last_keepalive >= keepalive_seconds:
                yield ": keep-alive\n\n"
                last_keepalive = time.time()

            time.sleep(0.2)


progress_store = JobProgressStore()
