"""
Core transcription logic.

Steps:
    1. normalize_audio(): use ffmpeg to convert any input format into a
       standard 16kHz mono WAV. This solves "different audio formats" by
       making everything downstream deal with a single consistent format,
       instead of every consumer needing to handle WAV/MP3/M4A/FLAC differently.
    2. chunk_audio(): for long files, split into fixed-length chunks (default
       5 minutes) with a small overlap, so we avoid timeouts/memory blowups
       and can process pieces independently (in parallel, if desired).
    3. transcribe_chunk(): runs Whisper on a chunk and returns segments with
       start/end timestamps.
    4. transcribe_file(): orchestrates the above and offsets timestamps from
       each chunk so the final segment list reflects time in the original file.

Whisper is loaded lazily so importing this module doesn't require the model
weights to be present (useful for testing other parts of the pipeline without
a network connection / GPU).
"""

import math
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict

CHUNK_SECONDS = 5 * 60  # 5 minutes
CHUNK_OVERLAP_SECONDS = 2

_model = None


def _get_model():
    """Lazily load the Whisper model (downloads weights on first use)."""
    global _model
    if _model is None:
        import whisper  # openai-whisper
        _model = whisper.load_model("base")
    return _model


def normalize_audio(input_path: str, output_path: str) -> str:
    """Convert any supported input format to 16kHz mono WAV via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def get_duration_seconds(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def chunk_audio(normalized_path: str, work_dir: str) -> List[Dict]:
    """
    Split a normalized WAV into fixed-length chunks with slight overlap.
    Returns a list of {"path": ..., "offset": start_time_in_original_file}.
    """
    duration = get_duration_seconds(normalized_path)
    chunks = []

    if duration <= CHUNK_SECONDS:
        return [{"path": normalized_path, "offset": 0.0}]

    n_chunks = math.ceil(duration / CHUNK_SECONDS)
    for i in range(n_chunks):
        start = max(0, i * CHUNK_SECONDS - (CHUNK_OVERLAP_SECONDS if i > 0 else 0))
        length = CHUNK_SECONDS + CHUNK_OVERLAP_SECONDS
        chunk_path = str(Path(work_dir) / f"chunk_{i}.wav")
        cmd = [
            "ffmpeg", "-y", "-i", normalized_path,
            "-ss", str(start), "-t", str(length),
            "-ar", "16000", "-ac", "1",
            chunk_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        chunks.append({"path": chunk_path, "offset": start})

    return chunks


def transcribe_chunk(chunk_path: str) -> List[Dict]:
    model = _get_model()
    result = model.transcribe(chunk_path, verbose=False)
    return [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
        for seg in result["segments"]
    ]


def transcribe_file(input_path: str) -> List[Dict]:
    """
    Full pipeline: normalize -> chunk -> transcribe each chunk -> merge,
    offsetting timestamps so they're relative to the original file.
    """
    with tempfile.TemporaryDirectory() as work_dir:
        normalized_path = str(Path(work_dir) / "normalized.wav")
        normalize_audio(input_path, normalized_path)

        chunks = chunk_audio(normalized_path, work_dir)

        all_segments: List[Dict] = []
        for chunk in chunks:
            segments = transcribe_chunk(chunk["path"])
            for seg in segments:
                all_segments.append({
                    "start": round(seg["start"] + chunk["offset"], 2),
                    "end": round(seg["end"] + chunk["offset"], 2),
                    "text": seg["text"],
                })

        # Merge overlap: drop segments from a later chunk that duplicate
        # the tail of the previous chunk (simple de-dupe by start time).
        all_segments.sort(key=lambda s: s["start"])
        deduped = []
        for seg in all_segments:
            if deduped and abs(seg["start"] - deduped[-1]["start"]) < 0.5 and seg["text"] == deduped[-1]["text"]:
                continue
            deduped.append(seg)

        return deduped
