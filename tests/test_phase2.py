"""Phase 2 tests. ffmpeg is real; ComfyUI is replaced by a fake client, so no GPU is needed."""
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import pipeline.batch as batch
from pipeline.metrics import flicker_report
from pipeline.video import extract_frames, encode, has_audio


@pytest.fixture(scope="session")
def clip(tmp_path_factory) -> Path:
    """2 s, 24 fps test clip with a 440 Hz tone."""
    p = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=24",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(p)],
        check=True,
    )
    return p


def test_extract_frame_count_and_resume(clip, tmp_path):
    assert extract_frames(clip, tmp_path / "f", fps=12) == 24
    (tmp_path / "f" / "frame_00001.png").write_bytes(b"sentinel")
    assert extract_frames(clip, tmp_path / "f", fps=12) == 24          # second call does no work
    assert (tmp_path / "f" / "frame_00001.png").read_bytes() == b"sentinel"


def test_extract_slice(clip, tmp_path):
    assert extract_frames(clip, tmp_path / "f", fps=12, start=0.5, seconds=1) == 12


def test_encode_keeps_audio_and_duration(clip, tmp_path):
    extract_frames(clip, tmp_path / "f", fps=12, seconds=1)
    out = encode(tmp_path / "f", tmp_path / "o.mp4", 12, clip, 0, 1)
    assert has_audio(out)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True,
    ).stdout
    assert float(dur) == pytest.approx(1.0, abs=0.15)


def test_encode_odd_dimensions(tmp_path):
    d = tmp_path / "f"
    d.mkdir()
    for i in range(1, 4):
        Image.new("RGB", (101, 75), (i * 40, 0, 0)).save(d / f"frame_{i:05d}.png")
    assert encode(d, tmp_path / "o.mp4", 12).exists()                   # no audio source: still works


class FakeClient:
    """Stands in for ComfyClient: 'stylizing' just copies the uploaded frame."""
    calls = 0

    def __init__(self, url):
        pass

    def is_up(self):
        return True

    def upload_image(self, path):
        self._src = path
        return path.name

    def queue(self, wf):
        FakeClient.calls += 1
        if FakeClient.calls == FakeClient.fail_on:
            raise RuntimeError("boom")
        return "id"

    def wait(self, pid):
        return {}

    def download_outputs(self, entry, out_dir, names):
        for node, rel in names.items():
            dest = out_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self._src.read_bytes())


CFG = {"comfyui": {"url": "x"}}


def test_stylize_resumes_after_crash(clip, tmp_path, monkeypatch):
    monkeypatch.setattr(batch, "ComfyClient", FakeClient)
    monkeypatch.setattr(batch, "build_workflow", lambda cfg, name, size, seed, denoise: {})
    extract_frames(clip, tmp_path / "frames" / "s", fps=12, seconds=1)    # 12 frames
    FakeClient.calls, FakeClient.fail_on = 0, 6
    with pytest.raises(RuntimeError):
        batch.stylize_shot(CFG, tmp_path, "s")
    assert len(list((tmp_path / "anime" / "s").glob("*.png"))) == 5       # frames 1-5 finished
    FakeClient.calls, FakeClient.fail_on = 0, -1
    assert batch.stylize_shot(CFG, tmp_path, "s") == 7                    # only the missing ones
    assert len(list((tmp_path / "lineart" / "s").glob("*.png"))) == 12


def test_flicker_metric_ranks_noise_worse(tmp_path):
    rng = np.random.default_rng(0)
    base = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    for name, noise in (("steady", 0), ("noisy", 80)):
        d = tmp_path / name
        d.mkdir()
        for i in range(1, 6):
            f = np.clip(base + rng.integers(-noise, noise + 1, base.shape) if noise else base, 0, 255)
            Image.fromarray(f.astype(np.uint8)).save(d / f"frame_{i:05d}.png")
    r = flicker_report(tmp_path / "steady", tmp_path / "noisy")
    assert r["source_ssim"] == pytest.approx(1.0) and r["ratio"] < 0.8
