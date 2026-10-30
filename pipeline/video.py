"""ffmpeg wrappers: split a clip into frames (ingest) and join frames back into a video (encode)."""
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"{cmd[0]} failed:\n{r.stderr[-2000:]}")


def has_audio(video: Path) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def extract_frames(video: Path, out_dir: Path, fps: float, start: float = 0, seconds: float | None = None) -> int:
    """Write out_dir/frame_00001.png ... at `fps`. Skips work if frames already exist (resumable)."""
    existing = sorted(out_dir.glob("frame_*.png"))
    if existing:
        return len(existing)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-i", str(video)]
    if seconds is not None:
        cmd += ["-t", str(seconds)]
    cmd += ["-vf", f"fps={fps}", str(out_dir / "frame_%05d.png")]
    _run(cmd)
    return len(list(out_dir.glob("frame_*.png")))


def encode(frames_dir: Path, out_file: Path, fps: float, audio_from: Path | None = None,
           start: float = 0, seconds: float | None = None) -> Path:
    """Encode frame_%05d.png to H.264, muxing the matching slice of audio_from's audio if it has any."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", str(frames_dir / "frame_%05d.png")]
    with_audio = audio_from is not None and has_audio(audio_from)
    if with_audio:
        cmd += ["-ss", str(start)]
        if seconds is not None:
            cmd += ["-t", str(seconds)]
        cmd += ["-i", str(audio_from)]
    # yuv420p needs even dimensions
    cmd += ["-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"]
    cmd.append(str(out_file))
    _run(cmd)
    return out_file
