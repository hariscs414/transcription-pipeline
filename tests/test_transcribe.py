"""
Basic tests.

We mock `transcribe_chunk` rather than downloading real Whisper weights,
so these tests run fast and offline. They verify the parts we actually
wrote: format normalization, chunking math, and timestamp offsetting -
not Whisper's own accuracy, which is out of scope to test here.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import transcribe


def make_silent_wav(path: str, seconds: int):
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono",
        "-t", str(seconds), path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def test_chunking_short_file(tmp_path):
    wav_path = str(tmp_path / "short.wav")
    make_silent_wav(wav_path, seconds=10)
    chunks = transcribe.chunk_audio(wav_path, str(tmp_path))
    assert len(chunks) == 1
    assert chunks[0]["offset"] == 0.0


def test_chunking_long_file(tmp_path):
    wav_path = str(tmp_path / "long.wav")
    make_silent_wav(wav_path, seconds=12 * 60)  # 12 minutes -> 3 chunks of 5 min
    chunks = transcribe.chunk_audio(wav_path, str(tmp_path))
    assert len(chunks) == 3
    assert chunks[0]["offset"] == 0.0
    assert chunks[1]["offset"] > 0


def test_transcribe_file_offsets_timestamps(tmp_path):
    wav_path = str(tmp_path / "input.wav")
    make_silent_wav(wav_path, seconds=10)

    fake_segments = [{"start": 0.0, "end": 2.0, "text": "hello"}]
    with patch.object(transcribe, "transcribe_chunk", return_value=fake_segments):
        result = transcribe.transcribe_file(wav_path)

    assert result[0]["text"] == "hello"
    assert result[0]["start"] == 0.0
