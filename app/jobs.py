"""
Job tracking.

For this assignment an in-memory dict stands in for a real database.
In production this would be a Postgres table (see README: "How would
you store audio and transcripts?") with columns mirroring the Job
fields below, so status survives restarts and can be queried by
multiple worker/API processes.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Job:
    job_id: str
    original_filename: str
    audio_path: str
    status: JobStatus = JobStatus.QUEUED
    result: Optional[List[dict]] = None
    error: Optional[str] = None
    retries: int = 0
    max_retries: int = 3


class JobStore:
    """Thread-safe-ish in-memory store. Replace with a DB-backed repo for production."""

    def __init__(self):
        self._jobs: Dict[str, Job] = {}

    def create(self, job_id: str, original_filename: str, audio_path: str) -> Job:
        job = Job(job_id=job_id, original_filename=original_filename, audio_path=audio_path)
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update_status(self, job_id: str, status: JobStatus):
        if job_id in self._jobs:
            self._jobs[job_id].status = status

    def set_result(self, job_id: str, segments: List[dict]):
        job = self._jobs[job_id]
        job.result = segments
        job.status = JobStatus.DONE

    def set_failed(self, job_id: str, error: str):
        job = self._jobs[job_id]
        job.error = error
        job.status = JobStatus.FAILED

    def increment_retry(self, job_id: str) -> int:
        job = self._jobs[job_id]
        job.retries += 1
        return job.retries
