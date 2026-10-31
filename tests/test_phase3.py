"""Phase 3 tests: flow-warp deflicker. CPU only; no GPU or ComfyUI."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline.metrics import static_region_flicker
from pipeline.shot_state import SettingsChanged
from pipeline.temporal import blend_frame, deflicker_shot

CFG = {"temporal": {"strength": 0.6, "error_threshold": 25}}


def _write(folder: Path, frames: list[np.ndarray]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames, 1):
        cv2.imwrite(str(folder / f"frame_{i:05d}.png"), f)


def _shot(tmp_path: Path, n: int = 6):
    """A still textured source and a stylized version with random per-frame noise (pure flicker)."""
    rng = np.random.default_rng(0)
    base = cv2.GaussianBlur(rng.integers(0, 255, (96, 96, 3), dtype=np.uint8), (0, 0), 3)
    noisy = [np.clip(base.astype(int) + rng.integers(-30, 30, base.shape), 0, 255).astype(np.uint8) for _ in range(n)]
    _write(tmp_path / "frames" / "s", [base] * n)
    _write(tmp_path / "anime" / "s", noisy)
    return base, noisy


def test_deflicker_reduces_flicker_on_a_still_source(tmp_path):
    _shot(tmp_path)
    assert deflicker_shot(CFG, tmp_path, "s") == 6
    before = static_region_flicker(tmp_path / "frames" / "s", tmp_path / "anime" / "s", size=(96, 96))
    after = static_region_flicker(tmp_path / "frames" / "s", tmp_path / "deflicker" / "s", size=(96, 96))
    assert after["static_diff"] < before["static_diff"] * 0.8


def test_first_frame_is_unchanged_and_resume_skips_done_frames(tmp_path):
    _, noisy = _shot(tmp_path)
    deflicker_shot(CFG, tmp_path, "s")
    assert np.array_equal(cv2.imread(str(tmp_path / "deflicker" / "s" / "frame_00001.png")), noisy[0])
    (tmp_path / "deflicker" / "s" / "frame_00006.png").unlink()
    assert deflicker_shot(CFG, tmp_path, "s") == 1


def test_changed_settings_stop_and_touch_nothing(tmp_path):
    _shot(tmp_path)
    deflicker_shot(CFG, tmp_path, "s")
    before = (tmp_path / "deflicker" / "s" / "frame_00003.png").read_bytes()
    with pytest.raises(SettingsChanged, match="temporal.strength"):
        deflicker_shot({"temporal": {"strength": 0.9, "error_threshold": 25}}, tmp_path, "s")
    assert (tmp_path / "deflicker" / "s" / "frame_00003.png").read_bytes() == before


def test_untrusted_warp_keeps_the_fresh_frame():
    """If the source changed completely (a cut), the previous output must not bleed in."""
    rng = np.random.default_rng(1)
    a, b = (rng.integers(0, 255, (64, 64, 3), dtype=np.uint8) for _ in range(2))
    anime = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
    out = blend_frame(anime, np.zeros_like(anime), b, a, strength=0.6, error_threshold=25)
    assert np.abs(out.astype(int) - anime.astype(int)).mean() < 3


def test_lowpass_blend_keeps_the_fresh_frames_fine_detail():
    """With sigma > 0 a still source pulls colors toward the previous output but leaves edges alone."""
    rng = np.random.default_rng(2)
    src = cv2.GaussianBlur(rng.integers(0, 255, (96, 96, 3), dtype=np.uint8), (0, 0), 3)
    anime = src.copy(); anime[:, 48:] = 255 - anime[:, 48:]     # a hard edge in the fresh frame
    prev = np.full_like(anime, 128)                              # flat previous output
    full = blend_frame(anime, prev, src, src, 0.8, 25)
    low = blend_frame(anime, prev, src, src, 0.8, 25, sigma=3)
    edge = lambda x: np.abs(np.diff(x[:, 40:56].astype(int), axis=1)).max()
    assert edge(low) > 2 * edge(full) and edge(low) > 0.8 * edge(anime)


# ---- AnimateDiff cloud stage (ComfyUI is faked; the real graph needs a GPU) ----
import copy

import pipeline.animatediff as ad
from pipeline.stylize import load_config
from pipeline.temporal import output_stage


def _refs_resolve(wf: dict) -> bool:
    return all(v[0] in wf for node in wf.values() for v in node["inputs"].values()
               if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str))


def test_animatediff_graph_with_ip_adapter(tmp_path):
    cfg = load_config()
    wf = ad.build_workflow(cfg, tmp_path, "ref.png", (1080, 1920))
    assert _refs_resolve(wf)
    assert wf["2"]["inputs"]["directory"] == str(tmp_path)
    assert wf["14"]["inputs"]["image"] == "ref.png" and wf["16"]["inputs"]["weight"] == cfg["animatediff"]["ip_adapter"]["weight"]
    assert wf["10"]["inputs"]["model"] == ["18", 0] and wf["18"]["inputs"]["model"] == ["16", 0]
    assert wf["7"]["inputs"]["resolution"] % 8 == 0


def test_animatediff_graph_without_ip_adapter(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["animatediff"]["ip_adapter"]["enabled"] = False
    wf = ad.build_workflow(cfg, tmp_path, None, (1080, 1920))
    assert _refs_resolve(wf) and not set(ad.IP_NODES) & set(wf)
    assert wf["18"]["inputs"]["model"] == ["1", 0]


class FakeAD:
    """ComfyClient stand-in: 'generates' one output image per source frame."""
    n = 0

    def __init__(self, url): pass
    def is_up(self): return True
    def upload_image(self, path): return path.name
    def queue(self, wf): return "id"
    def wait(self, pid, timeout=0): return {}
    missing = []
    def missing_nodes(self, wf): return FakeAD.missing

    def download_outputs(self, entry, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(FakeAD.n):
            p = out_dir / f"animatediff_{i + 1:05d}_.png"
            cv2.imwrite(str(p), np.full((8, 8, 3), i, np.uint8))
            paths.append(p)
        return {"12": paths}


def _ad_shot(tmp_path, n=5):
    _write(tmp_path / "frames" / "s", [np.zeros((32, 32, 3), np.uint8)] * n)
    FakeAD.n = n


def test_animatediff_shot_names_results_after_source_frames(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "ComfyClient", FakeAD)
    _ad_shot(tmp_path)
    assert ad.animatediff_shot(load_config(), tmp_path, "s") == 5
    out = tmp_path / "animatediff" / "s"
    assert [f.name for f in sorted(out.glob("frame_*.png"))] == [f"frame_{i:05d}.png" for i in range(1, 6)]
    assert not (out / "_download").exists()
    assert ad.animatediff_shot(load_config(), tmp_path, "s") == 0   # done: nothing to redo


def test_animatediff_wrong_frame_count_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "ComfyClient", FakeAD)
    _ad_shot(tmp_path)
    FakeAD.n = 3
    with pytest.raises(RuntimeError, match="3 frames for 5"):
        ad.animatediff_shot(load_config(), tmp_path, "s")
    assert not list((tmp_path / "animatediff" / "s").glob("frame_*.png"))


def test_animatediff_changed_settings_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "ComfyClient", FakeAD)
    _ad_shot(tmp_path)
    ad.animatediff_shot(load_config(), tmp_path, "s")
    with pytest.raises(SettingsChanged, match="ip_adapter.weight"):
        cfg = copy.deepcopy(load_config())
        cfg["animatediff"]["ip_adapter"]["weight"] = 0.9
        ad.animatediff_shot(cfg, tmp_path, "s")


def test_deflicker_can_read_the_animatediff_stage(tmp_path):
    _shot(tmp_path)
    (tmp_path / "animatediff").mkdir()
    (tmp_path / "anime" / "s").rename(tmp_path / "animatediff" / "s")
    assert deflicker_shot(CFG, tmp_path, "s", source="animatediff") == 6
    assert output_stage("animatediff") == "deflicker_animatediff" and output_stage("anime") == "deflicker"
    assert (tmp_path / "deflicker_animatediff" / "s" / "frame_00006.png").exists()


def test_animatediff_graph_uses_sliding_window_safe_controlnet_nodes(tmp_path):
    """The stock ControlNet nodes fail with AnimateDiff's context windows (found by running it for real)."""
    wf = ad.build_workflow(load_config(), tmp_path, "ref.png", (1080, 1920))
    assert wf["6"]["class_type"] == "ACN_ControlNetLoaderAdvanced" and wf["6"]["inputs"]["cnet"].endswith(".safetensors")
    assert wf["8"]["class_type"] == "ACN_AdvancedControlNetApply_v2"


def test_animatediff_names_missing_custom_nodes_instead_of_queueing(tmp_path, monkeypatch):
    monkeypatch.setattr(ad, "ComfyClient", FakeAD)
    monkeypatch.setattr(FakeAD, "missing", ["ACN_ControlNetLoaderAdvanced"])
    _ad_shot(tmp_path)
    with pytest.raises(RuntimeError, match="ACN_ControlNetLoaderAdvanced.*RESTART"):
        ad.animatediff_shot(load_config(), tmp_path, "s")
    assert not list((tmp_path / "animatediff" / "s").glob("frame_*.png"))
