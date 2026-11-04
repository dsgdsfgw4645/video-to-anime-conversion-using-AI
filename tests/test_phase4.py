"""Phase 4 tests: style-frame extraction from a film. CPU only."""
import cv2
import numpy as np
import pytest

from pipeline.shot_state import SettingsChanged
from pipeline.style_frames import extract_style_frames, find_video


def _film(path, scenes=6, per_scene=40, fps=10):
    """Letterboxed synthetic film: each scene is a different textured colour field."""
    rng = np.random.default_rng(1)
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
    for s in range(scenes):
        base = cv2.GaussianBlur(rng.integers(0, 255, (160, 320, 3), dtype=np.uint8), (0, 0), 4)
        base = cv2.normalize(base, None, 40, 220, cv2.NORM_MINMAX)
        base = np.clip((base.astype(int) - 130) * 3 + 130, 30, 225).astype(np.uint8)
        base[..., s % 3] = np.clip(base[..., s % 3].astype(int) + 30 * s, 0, 255)
        for _ in range(per_scene):
            f = np.zeros((240, 320, 3), np.uint8)
            f[40:200] = base
            w.write(f)
    w.release()


def test_extracts_cropped_distinct_frames(tmp_path):
    film = tmp_path / "film.avi"
    _film(film)
    out = tmp_path / "images"
    n = extract_style_frames(film, out, {"skip_start_pct": 0, "skip_end_pct": 0, "sample_interval": 0.5}, log=lambda *_: None)
    assert 3 <= n <= 6
    im = cv2.imread(str(sorted(out.glob("frame_*.png"))[0]))
    assert im.shape[0] <= 164 and im.shape[1] == 320      # 160-row picture; the black bars are cropped
    assert (out / "contact_sheet.jpg").exists()


def test_rerun_resumes_and_changed_settings_stop(tmp_path):
    film = tmp_path / "film.avi"
    _film(film)
    out = tmp_path / "images"
    p = {"skip_start_pct": 0, "skip_end_pct": 0}
    n = extract_style_frames(film, out, p, log=lambda *_: None)
    assert extract_style_frames(film, out, p, log=lambda *_: None) == n
    with pytest.raises(SettingsChanged):
        extract_style_frames(film, out, {**p, "max_images": 2}, log=lambda *_: None)
    assert len(list(out.glob("frame_*.png"))) == n


def test_find_video_takes_largest(tmp_path):
    (tmp_path / "a.mkv").write_bytes(b"x" * 10)
    (tmp_path / "b.mp4").write_bytes(b"x" * 100)
    (tmp_path / "c.txt").write_bytes(b"x" * 1000)
    assert find_video(tmp_path).name == "b.mp4"
    assert find_video(tmp_path / "nope") is None
