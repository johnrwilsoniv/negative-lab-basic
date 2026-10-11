"""A roll folder: raw captures plus `roll.json` (settings and per-frame edits)."""
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from nlb.heic import RAW_SUFFIXES

DEFAULT_SETTINGS = {"film": "c41", "flip": False, "base": None, "levels": None}
FRAME_KEYS = {"crop", "rotation", "angle", "rejected", "params", "engine"}
ROTATIONS = (0, 90, 180, 270)
ENGINES = ("nlb", "darktable")  # how a frame is developed; a missing "engine" means nlb


class Roll:
    """Thread-safe view of a roll folder. `roll.json` is rewritten atomically on every change."""

    def __init__(self, folder: Path, prefix: str = "frame"):
        self.folder = folder.resolve()
        self.prefix = prefix
        self.json_path = self.folder / "roll.json"
        self.trash = self.folder / ".nlb" / "trash"
        self.lock = threading.RLock()
        self.version = 0
        self.folder.mkdir(parents=True, exist_ok=True)
        data = json.loads(self.json_path.read_text()) if self.json_path.exists() else {}
        self.settings = {**DEFAULT_SETTINGS, **data.get("settings", {})}
        self.frames: dict[str, dict] = data.get("frames", {})
        self.camera: dict = data.get("camera", {})
        if not self.scan() and not self.json_path.exists():
            self._save()  # marks an empty folder as a roll

    # --- files ---

    def scan(self) -> bool:
        """Sync frames with the raw files on disk; True if anything changed."""
        with self.lock:
            files = {p.stem: p.name for p in sorted(self.folder.iterdir())
                     if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in RAW_SUFFIXES}
            changed = False
            for stem, name in files.items():
                if stem not in self.frames:
                    self.frames[stem] = new_frame(name)
                    changed = True
                elif self.frames[stem].get("file") != name:
                    self.frames[stem]["file"] = name
                    changed = True
            for stem in [s for s in self.frames if s not in files]:
                # raw gone (deleted or moved by hand): forget its edits
                del self.frames[stem]
                changed = True
            self.frames = dict(sorted(self.frames.items()))
            if changed:
                self._save()
            return changed

    def path(self, name: str) -> Path:
        return self.folder / self.frames[name]["file"]

    def next_name(self) -> str:
        """`<prefix>-NNN`, one past the highest existing number (trash included, so names never repeat)."""
        pat = re.compile(rf"^{re.escape(self.prefix)}-(\d+)$")
        stems = [p.stem for d in (self.folder, self.trash) if d.is_dir() for p in d.iterdir()]
        nums = [int(m.group(1)) for s in stems if (m := pat.match(s))]
        return f"{self.prefix}-{max(nums, default=0) + 1:03d}"

    def add_capture(self, src: Path, name: str) -> str:
        """Move a downloaded file into the roll as `<name><suffix>`; returns the frame name."""
        with self.lock:
            dest = self.folder / f"{name}{src.suffix.upper()}"
            shutil.move(src, dest)
            if dest.suffix.lower() in RAW_SUFFIXES:
                self.frames[name] = new_frame(dest.name)
                self.frames = dict(sorted(self.frames.items()))
                self._save()
            return name

    def discard(self, name: str) -> None:
        """Move a frame's files (raw plus same-stem sidecars) to `.nlb/trash/`; never deletes.

        Trashed names get a timestamp so a reshoot can reuse the frame name.
        """
        with self.lock:
            self.trash.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            for p in self.folder.glob(f"{glob_escape(name)}.*"):
                if p.name != "roll.json":
                    shutil.move(p, self.trash / f"{p.stem}.{stamp}{p.suffix}")
            self.frames.pop(name, None)
            self._save()

    # --- edits ---

    def update_settings(self, patch: dict) -> None:
        with self.lock:
            for k, v in patch.items():
                if k == "film" and v not in ("c41", "bw"):
                    raise ValueError("film must be c41 or bw")
                if k == "flip":
                    v = bool(v)
                self.settings[k] = v
            self._save()

    def update_frame(self, name: str, patch: dict) -> dict:
        with self.lock:
            frame = self.frames[name]
            for k, v in patch.items():
                if k not in FRAME_KEYS:
                    raise ValueError(f"unknown frame field {k!r}")
                if k == "rotation" and v not in ROTATIONS:
                    raise ValueError(f"rotation must be one of {ROTATIONS}")
                if k == "engine" and v not in ENGINES:
                    raise ValueError(f"engine must be one of {ENGINES}")
                if k == "crop":
                    v = clamp_crop(v)
                if k == "angle":
                    v = max(-5.0, min(5.0, float(v)))
                if k == "params":
                    v = {**frame.get("params", {}), **{pk: float(pv) for pk, pv in v.items()}}
                frame[k] = v
            self._save()
            return frame

    def set_camera(self, info: dict) -> None:
        with self.lock:
            self.camera = info
            self._save()

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps({"settings": self.settings, "frames": self.frames,
                                          "camera": self.camera}))

    def _save(self) -> None:
        self.version += 1
        tmp = self.json_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"version": 1, "settings": self.settings, "camera": self.camera,
                                   "frames": self.frames}, indent=2))
        os.replace(tmp, self.json_path)


def new_frame(file: str) -> dict:
    return {"file": file, "crop": None, "rotation": 0, "angle": 0.0, "rejected": False, "params": {}}


def clamp_crop(crop) -> list[float]:
    x, y, w, h = (float(v) for v in crop)
    x, y = min(max(x, 0.0), 0.99), min(max(y, 0.0), 0.99)
    w, h = min(max(w, 0.01), 1.0 - x), min(max(h, 0.01), 1.0 - y)
    return [round(v, 5) for v in (x, y, w, h)]


def glob_escape(s: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", s)
