"""
FastAPI service for the transcription pipeline.

Endpoints:
    POST /transcribe          -> upload an audio file, returns a job_id immediately
    GET  /transcription/{id}  -> poll job status / get result when done
    GET  /health              -> health check

Design:
    Upload and processing are decoupled. The upload endpoint only validates
    the file, saves it to disk (storage.py), and enqueues a background job.
    A worker (worker.py) consumes the queue and runs the actual transcription
    (transcribe.py). This keeps the API responsive under concurrent uploads
    and lets transcription scale independently (e.g. multiple worker processes).
"""

import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app import storage
from app.jobs import JobStore, JobStatus
from app.worker import enqueue_job

app = FastAPI(title="Transcription Pipeline")

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
MAX_FILE_SIZE_MB = 100

job_store = JobStore()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=400, detail="File exceeds 100MB limit")

    job_id = str(uuid.uuid4())
    audio_path = storage.save_audio(job_id, file.filename, contents)

    job_store.create(job_id, original_filename=file.filename, audio_path=str(audio_path))

    # Enqueue for async processing instead of blocking the request.
    enqueue_job(job_id, str(audio_path), job_store)

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": JobStatus.QUEUED.value},
    )


@app.get("/transcription/{job_id}")
def get_transcription(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job.status.value,
        "filename": job.original_filename,
        "retries": job.retries,
    }
    if job.status == JobStatus.DONE:
        response["segments"] = job.result
    if job.status == JobStatus.FAILED:
        response["error"] = job.error

    return response
