from pathlib import Path

STORAGE_ROOT = Path(__file__).resolve().parent.parent / "storage" / "audio"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def save_audio(job_id: str, original_filename: str, contents: bytes) -> Path:
    ext = Path(original_filename).suffix.lower()
    dest = STORAGE_ROOT / f"{job_id}{ext}"
    dest.write_bytes(contents)
    return dest
