"""Record the settings a shot's frames were made with, so a shot is never overwritten by accident.

Each stage folder (frames/<shot>, anime/<shot>) gets a settings.json. On the next run the stored
settings are compared with the current ones: equal means resume (skip finished frames), different
means SettingsChanged is raised and nothing is deleted or overwritten. A shot with frames but no
record (made before tracking) counts as different. To try new settings, use a new shot name.
"""
import json
from pathlib import Path

SETTINGS = "settings.json"


class SettingsChanged(RuntimeError):
    """The shot already has frames made with different settings; the run must stop."""


def prepare(folder: Path, current: dict) -> None:
    """Check folder's recorded settings against `current`, then record `current` there.

    Raises SettingsChanged, before changing anything, if the folder already holds frames made
    with other settings.
    """
    current = json.loads(json.dumps(current))  # same types as a stored copy (tuples -> lists etc.)
    record = folder / SETTINGS
    if any(folder.glob("frame_*.png")):
        old = json.loads(record.read_text(encoding="utf-8")) if record.exists() else None
        if old == current:
            return
        raise SettingsChanged(_message(folder, old, current))
    folder.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(current, indent=2), encoding="utf-8")


def _message(folder: Path, old: dict | None, new: dict) -> str:
    return (f"Stopped: {folder} already holds frames made with different settings ({_reason(old, new)}). "
            "Nothing was changed. Set a new shot name (input.shot in the config, or --shot) and run again; "
            "to keep using this shot, change the settings back.")


def _reason(old: dict | None, new: dict) -> str:
    if old is None:
        return "no settings were recorded for them, they were made before settings tracking"
    old, new = _flatten(old), _flatten(new)
    keys = [k for k in sorted(old.keys() | new.keys()) if old.get(k) != new.get(k)]
    return "changed: " + ", ".join(f"{k} {_short(old.get(k))} -> {_short(new.get(k))}" for k in keys)


def _flatten(d: dict, prefix: str = "") -> dict:
    """{"sampling": {"denoise": 0.4}} -> {"sampling.denoise": 0.4}, so the message names the exact setting."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(_flatten(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def _short(value: object, limit: int = 60) -> str:
    text = json.dumps(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."
