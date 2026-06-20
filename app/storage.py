"""
Audio storage.

Locally, files are written under ./storage/audio/{job_id}{ext}.
In production this would be replaced with an S3 (or GCS) upload —
the function signature stays the same, only the implementation
of save_audio changes, so the rest of the app doesn't need to know
where bytes physically live.
"""

from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage" / "audio"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def save_audio(job_id: str, original_filename: str, contents: bytes) -> Path:
    ext = Path(original_filename).suffix.lower()
    dest = STORAGE_ROOT / f"{job_id}{ext}"
    dest.write_bytes(contents)
    return dest
