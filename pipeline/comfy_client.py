"""Thin client for ComfyUI's HTTP API: upload an image, queue a workflow, fetch outputs."""
import json
import time
import uuid
from pathlib import Path

import requests


class ComfyClient:
    def __init__(self, url: str = "http://127.0.0.1:8188") -> None:
        self.url = url.rstrip("/")
        self.client_id = uuid.uuid4().hex

    def is_up(self) -> bool:
        try:
            return requests.get(f"{self.url}/system_stats", timeout=3).ok
        except requests.RequestException:
            return False

    def missing_nodes(self, workflow: dict) -> list[str]:
        """Node types the workflow uses that the running ComfyUI doesn't have (custom node not installed, or
        installed after ComfyUI started: a running server never sees new nodes until it is restarted)."""
        r = requests.get(f"{self.url}/object_info", timeout=60)
        r.raise_for_status()
        return sorted({n["class_type"] for n in workflow.values()} - r.json().keys())

    def upload_image(self, path: Path, name: str | None = None) -> str:
        """Upload to ComfyUI's input folder (as `name`, default the file's own) and return the name to use in a LoadImage node."""
        with open(path, "rb") as f:
            r = requests.post(
                f"{self.url}/upload/image",
                files={"image": (name or path.name, f)},
                data={"overwrite": "true"},
            )
        r.raise_for_status()
        return r.json()["name"]

    def queue(self, workflow: dict) -> str:
        r = requests.post(
            f"{self.url}/prompt",
            json={"prompt": workflow, "client_id": self.client_id},
        )
        if not r.ok:
            raise RuntimeError(f"ComfyUI rejected the workflow: {r.text}")
        return r.json()["prompt_id"]

    def wait(self, prompt_id: str, timeout: float = 600, poll: float = 1.0) -> dict:
        """Block until the prompt finishes and return its history entry."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{self.url}/history/{prompt_id}")
            r.raise_for_status()
            entry = r.json().get(prompt_id)
            if entry and entry.get("status", {}).get("completed") is not None:
                if entry["status"].get("status_str") == "error":
                    raise RuntimeError(json.dumps(entry["status"]["messages"][-1], indent=2))
                return entry
            time.sleep(poll)
        raise TimeoutError(f"prompt {prompt_id} did not finish in {timeout}s")

    def download_outputs(
        self, entry: dict, out_dir: Path, names: dict[str, str] | None = None
    ) -> dict[str, list[Path]]:
        """Save each output image and return the paths keyed by the id of the node that made them.

        names maps a node id to a path relative to out_dir (subfolders allowed), e.g.
        {"12": "anime/frame_00001.png"}. Nodes not listed keep ComfyUI's own file name.
        A node that saved several images gets _1, _2, ... added to the renamed files after the first.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        saved: dict[str, list[Path]] = {}
        for node_id, node_out in entry["outputs"].items():
            for i, img in enumerate(node_out.get("images", [])):
                r = requests.get(
                    f"{self.url}/view",
                    params={
                        "filename": img["filename"],
                        "subfolder": img["subfolder"],
                        "type": img["type"],
                    },
                )
                r.raise_for_status()
                if names and node_id in names:
                    dest = out_dir / names[node_id]
                    if i:
                        dest = dest.with_name(f"{dest.stem}_{i}{dest.suffix}")
                else:
                    dest = out_dir / img["filename"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                saved.setdefault(node_id, []).append(dest)
        return saved

    def run(
        self,
        workflow: dict,
        out_dir: Path,
        timeout: float = 600,
        names: dict[str, str] | None = None,
    ) -> dict[str, list[Path]]:
        entry = self.wait(self.queue(workflow), timeout=timeout)
        return self.download_outputs(entry, out_dir, names)
