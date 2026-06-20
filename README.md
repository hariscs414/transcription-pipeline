# Transcription Pipeline

A simple service that accepts an audio file, transcribes it to text with
per-segment timestamps, and returns the result via a REST API.

## Quick start

```bash
pip install -r requirements.txt
# requires ffmpeg installed on the system (apt install ffmpeg / brew install ffmpeg)
uvicorn app.main:app --reload
```

```bash
curl -F "file=@sample.mp3" http://localhost:8000/transcribe
# -> {"job_id": "...", "status": "queued"}

curl http://localhost:8000/transcription/<job_id>
# -> {"status": "done", "segments": [{"start": 0.0, "end": 2.1, "text": "..."}]}
```

## Project structure

```
app/
  main.py        FastAPI routes (upload, status, health)
  jobs.py        Job model + in-memory job store
  storage.py     Saves uploaded audio to disk
  transcribe.py  Format normalization, chunking, Whisper transcription
  worker.py      Background processing + retry logic
tests/
  test_transcribe.py   Tests for chunking/normalization (Whisper itself is mocked)
```

## Part 1 — Pipeline decisions

**Accepting audio.** Uploads go through `POST /transcribe`, which validates
extension (`.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`) and a 100MB size cap
before saving the file. Validation happens before any expensive work starts.

**Transcription.** Uses OpenAI's Whisper (`base` model) for speech-to-text.
It's open-source, multilingual, and ships with segment-level timestamps out
of the box, so it didn't make sense to build a custom timestamp aligner. The
Whisper call is isolated in `transcribe.py` behind a small function
interface, so swapping in a hosted API (e.g. AssemblyAI, Deepgram) later
only touches one file.

**Timestamps.** Whisper returns `start`/`end`/`text` per segment natively.
These are passed through as-is, with offsets applied during chunk merging
(see below) so they stay correct relative to the original file.

**Different audio formats.** Every input is normalized with `ffmpeg` to
16kHz mono WAV before transcription (`normalize_audio()`). This means the
rest of the pipeline only ever has to deal with one format, regardless of
whether the upload was MP3, M4A, FLAC, etc.

**Long audio files.** Files longer than 5 minutes are split into 5-minute
chunks with a 2-second overlap (`chunk_audio()`), each transcribed
independently, then merged back together with timestamps offset to match
their position in the original file. Overlapping/duplicate segments at chunk
boundaries are de-duped. This keeps memory bounded and avoids a single
huge transcription call timing out; chunks could also be processed in
parallel if needed.

## Part 2 — System design

**Concurrent uploads.** Upload and processing are decoupled. `POST
/transcribe` only validates and saves the file, then enqueues a job and
returns a `job_id` immediately (HTTP 202) — it does not wait for
transcription. A pool of workers consumes the queue separately, so the API
stays responsive no matter how many transcriptions are in flight. In this
repo that queue is a `ThreadPoolExecutor` for simplicity; in production I'd
use a real broker (Redis + RQ/Celery, or SQS) with one or more standalone
worker processes, so a crashed worker can't take down the API and workers
can be scaled horizontally under load.

**Storing audio and transcripts.** Audio bytes and structured data have
different access patterns, so I'd keep them separate:
- **Audio files** → object storage (S3 or equivalent). Cheap, durable,
  scales to large files without touching the database.
- **Transcripts + metadata** (status, timestamps, retry count, error
  messages, S3 key) → a relational database (e.g. Postgres). This repo's
  `JobStore` is an in-memory stand-in for that table — same fields, just
  not persisted to disk, so it resets if the process restarts.

**Retrying failed transcriptions.** Each job tracks a retry count. On
failure, the job is automatically resubmitted up to `max_retries` (3) times
before being marked `failed` with the error message stored for debugging.
In production I'd add exponential backoff between retries and a
dead-letter queue for jobs that exhaust retries, so they can be inspected
and manually replayed instead of silently disappearing.

**Exposing it as an API.** REST API via FastAPI:

| Method | Path                      | Purpose                                  |
|--------|---------------------------|-------------------------------------------|
| POST   | `/transcribe`              | Upload audio, returns `job_id` (202)      |
| GET    | `/transcription/{job_id}`  | Poll status / fetch result when done      |
| GET    | `/health`                  | Health check                              |

Large files don't block the request — the client gets a `job_id` right
away and polls (or, in a fuller version, the API could push a webhook /
websocket update when the job finishes instead of requiring polling).

## What I'd change for production

- Real queue (Redis/SQS) instead of an in-process thread pool.
- Postgres-backed `JobStore` instead of an in-memory dict.
- S3 for audio storage instead of local disk.
- Exponential backoff + dead-letter queue for retries.
- Auth on the API endpoints and per-user rate limiting on uploads.
- Parallelize chunk transcription within a single job for faster turnaround
  on long files.
