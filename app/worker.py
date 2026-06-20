from concurrent.futures import ThreadPoolExecutor

from app.jobs import JobStore, JobStatus
from app.transcribe import transcribe_file

_executor = ThreadPoolExecutor(max_workers=4)


def _process(job_id: str, audio_path: str, job_store: JobStore):
    job = job_store.get(job_id)
    job_store.update_status(job_id, JobStatus.PROCESSING)
    try:
        segments = transcribe_file(audio_path)
        job_store.set_result(job_id, segments)
    except Exception as exc:  # noqa: BLE001 - want to catch and retry any failure
        retries = job_store.increment_retry(job_id)
        if retries <= job.max_retries:
            # simple retry: resubmit the same job
            _executor.submit(_process, job_id, audio_path, job_store)
        else:
            job_store.set_failed(job_id, str(exc))


def enqueue_job(job_id: str, audio_path: str, job_store: JobStore):
    _executor.submit(_process, job_id, audio_path, job_store)
