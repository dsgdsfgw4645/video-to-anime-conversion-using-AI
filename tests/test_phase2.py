"""Phase 2 tests. ffmpeg is real; ComfyUI is replaced by a fake client, so no GPU is needed."""
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import pipeline.batch as batch
import pipeline.server as server
from pipeline.metrics import flicker_report
from pipeline.shot_state import SettingsChanged
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


CFG = {
    "comfyui": {"url": "x"},
    "models": {"checkpoint": "m.safetensors", "controlnet_lineart": "c.safetensors"},
    "style": {"positive": "anime", "negative": "photo"},
    "sampling": {"seed": 1, "steps": 4, "cfg": 7.0, "sampler": "euler", "scheduler": "normal", "denoise": 0.4},
    "controlnet": {"lineart_strength": 0.8},
    "video": {"work_fps": 12, "target_megapixels": 0.4},
}


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


def _fake_comfy(monkeypatch):
    monkeypatch.setattr(batch, "ComfyClient", FakeClient)
    monkeypatch.setattr(batch, "build_workflow", lambda cfg, name, size, seed, denoise: {})
    FakeClient.calls, FakeClient.fail_on = 0, -1


def _snapshot(folder: Path) -> dict:
    return {f.name: f.read_bytes() for f in folder.iterdir()}


def test_extract_stops_on_changed_settings_and_touches_nothing(clip, tmp_path):
    f = tmp_path / "f"
    assert extract_frames(clip, f, fps=12, seconds=1) == 12
    before = _snapshot(f)
    assert extract_frames(clip, f, fps=12, seconds=1) == 12                # same settings: reused
    with pytest.raises(SettingsChanged, match=r"start 0 -> 0\.5"):
        extract_frames(clip, f, fps=12, start=0.5, seconds=1)
    assert _snapshot(f) == before                                          # nothing deleted or rewritten


def test_stylize_stops_on_changed_denoise_or_seed_and_touches_nothing(clip, tmp_path, monkeypatch):
    _fake_comfy(monkeypatch)
    extract_frames(clip, tmp_path / "frames" / "s", fps=12, seconds=1)
    assert batch.stylize_shot(CFG, tmp_path, "s", denoise=0.4) == 12
    before = (_snapshot(tmp_path / "anime" / "s"), _snapshot(tmp_path / "lineart" / "s"))
    assert batch.stylize_shot(CFG, tmp_path, "s", denoise=0.4) == 0        # same settings: resume, nothing to do
    with pytest.raises(SettingsChanged, match=r"sampling\.denoise 0\.4 -> 0\.5"):
        batch.stylize_shot(CFG, tmp_path, "s", denoise=0.5)
    with pytest.raises(SettingsChanged, match=r"sampling\.seed"):
        batch.stylize_shot(CFG, tmp_path, "s", denoise=0.4, seed=99)
    assert (_snapshot(tmp_path / "anime" / "s"), _snapshot(tmp_path / "lineart" / "s")) == before


def test_stylize_stops_when_source_frames_differ(clip, tmp_path, monkeypatch):
    _fake_comfy(monkeypatch)
    extract_frames(clip, tmp_path / "frames" / "s", fps=12, seconds=1)
    batch.stylize_shot(CFG, tmp_path, "s")
    extract_frames(clip, tmp_path / "frames" / "t", fps=12, start=0.5, seconds=1)
    (tmp_path / "frames" / "s" / "settings.json").write_text(
        (tmp_path / "frames" / "t" / "settings.json").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(SettingsChanged, match=r"frames\.start"):
        batch.stylize_shot(CFG, tmp_path, "s")


def test_shot_without_a_settings_record_is_refused(clip, tmp_path):
    f = tmp_path / "f"
    extract_frames(clip, f, fps=12, seconds=1)
    (f / "settings.json").unlink()                                          # a shot made before tracking
    before = _snapshot(f)
    with pytest.raises(SettingsChanged, match="before settings tracking"):
        extract_frames(clip, f, fps=12, seconds=1)
    assert _snapshot(f) == before


def test_cli_stops_with_message_and_keeps_the_old_video(clip, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    import cli
    _fake_comfy(monkeypatch)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: {**CFG, "input": {"shot": "mine"}})
    runner = CliRunner()
    first = runner.invoke(cli.app, ["run", str(clip), "--seconds", "1", "--denoise", "0.4"])
    assert first.exit_code == 0, first.output
    out = tmp_path / "work" / "default" / "out" / "mine.mp4"
    before = (out.read_bytes(), _snapshot(tmp_path / "work" / "default" / "anime" / "mine"))
    again = runner.invoke(cli.app, ["run", str(clip), "--seconds", "1", "--denoise", "0.4"])
    assert again.exit_code == 0 and "stylized 0 new frames" in again.output
    second = runner.invoke(cli.app, ["run", str(clip), "--seconds", "1", "--denoise", "0.5"])
    assert second.exit_code == 1
    assert "different settings" in second.output and "new shot name" in second.output
    assert "wrote" not in second.output                                     # stopped before encoding
    assert (out.read_bytes(), _snapshot(tmp_path / "work" / "default" / "anime" / "mine")) == before


def test_cli_with_no_command_runs_the_config(clip, tmp_path, monkeypatch):
    from typer.testing import CliRunner
    import cli
    _fake_comfy(monkeypatch)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "in.mp4").write_bytes(clip.read_bytes())
    monkeypatch.setattr(cli, "load_config", lambda: {**CFG, "input": {"video": "in.mp4", "seconds": 1, "shot": "auto"}})
    result = CliRunner().invoke(cli.app, [])                                # what `python cli.py` does
    assert result.exit_code == 0, result.output
    assert (tmp_path / "work" / "default" / "out" / "auto.mp4").exists()


class _Proc:
    pid = 1

    def poll(self):
        return None


class _Client:
    """is_up() is False for the first `down_polls` calls, then True."""
    url = "http://127.0.0.1:8188"

    def __init__(self, down_polls):
        self.down = down_polls

    def is_up(self):
        self.down -= 1
        return self.down < 0


def _fake_server(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_start", lambda port: calls.append(("start", port)) or _Proc())
    monkeypatch.setattr(server, "_stop", lambda proc: calls.append(("stop",)))
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    return calls


def test_server_already_running_is_left_alone(monkeypatch):
    calls = _fake_server(monkeypatch)
    with server.comfy_server(_Client(0), {}):
        pass
    assert calls == []                                                     # not started, not stopped


def test_server_is_started_and_stopped_when_down(monkeypatch):
    calls = _fake_server(monkeypatch)
    with server.comfy_server(_Client(3), {"comfyui": {}}):
        assert calls == [("start", 8188)]
    assert calls == [("start", 8188), ("stop",)]


def test_server_is_stopped_even_if_the_work_fails(monkeypatch):
    calls = _fake_server(monkeypatch)
    with pytest.raises(ValueError):
        with server.comfy_server(_Client(1), {"comfyui": {}}):
            raise ValueError("boom")
    assert calls[-1] == ("stop",)


def test_autostop_false_leaves_it_running(monkeypatch):
    calls = _fake_server(monkeypatch)
    with server.comfy_server(_Client(1), {"comfyui": {"autostop": False}}):
        pass
    assert calls == [("start", 8188)]


def test_autostart_false_raises_instead_of_starting(monkeypatch):
    calls = _fake_server(monkeypatch)
    with pytest.raises(RuntimeError, match="not reachable"):
        with server.comfy_server(_Client(5), {"comfyui": {"autostart": False}}):
            pass
    assert calls == []


def test_nothing_to_stylize_never_needs_the_server(clip, tmp_path, monkeypatch):
    _fake_comfy(monkeypatch)
    extract_frames(clip, tmp_path / "frames" / "s", fps=12, seconds=1)
    batch.stylize_shot(CFG, tmp_path, "s")
    monkeypatch.setattr(server, "_start", lambda port: pytest.fail("server must not start"))
    monkeypatch.setattr(FakeClient, "is_up", lambda self: False)
    assert batch.stylize_shot(CFG, tmp_path, "s") == 0                     # all done: no server needed


def test_shot_name_priority():
    from cli import resolve_shot
    v = Path("samples/clip.mp4")
    assert resolve_shot("cli", {"shot": "cfg"}, v, "_preview") == "cli"      # --shot wins
    assert resolve_shot(None, {"shot": "cfg"}, v, "_preview") == "cfg"       # then the config
    assert resolve_shot(None, {}, v, "_preview") == "clip_preview"           # then the video name
    assert resolve_shot(None, {}, v) == "clip"


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
