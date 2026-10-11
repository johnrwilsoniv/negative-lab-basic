"""Tethered camera control on one worker thread (libgphoto2 is not thread-safe).

`CameraWorker` owns a backend: `GPhotoBackend` for a real camera (Sony A7 IV in PC Remote
mode, see sony-capture/README.md) or `FakeBackend`, which replays raw files from a folder.
Live view runs only while a browser is streaming it; otherwise the worker polls for
files added by pressing the shutter on the camera. With no camera connected it watches
for one to be plugged in and connects to it.
"""
import itertools
import queue
import shutil
import threading
import time
import traceback
from concurrent.futures import Future
from pathlib import Path

import rawpy

from nlb.heic import RAW_SUFFIXES

# Settings shown in the UI, in order. Missing ones are skipped.
CONFIG_KEYS = ("iso", "shutterspeed", "f-number", "imagequality", "pcsaveimgsize")
# Locked on connect: without these the A7 IV sends a 1616x1080 JPEG proxy instead of the raw.
REQUIRED_CONFIG = (("imagequality", "RAW"), ("pcsaveimgsize", "Original"))
NO_CAMERA = ("No camera found. Plug it in and turn it on (USB Connection Mode = PC Remote, "
             "USB Streaming off); it connects automatically.")
DETECT_EVERY = 2.0  # seconds between looks for a newly plugged-in camera


def gphoto_missing() -> str | None:
    """Why tethered capture can't work on this machine, or None if it can."""
    try:
        import gphoto2  # noqa: F401
    except ImportError as e:
        if e.name == "gphoto2":
            return ("Tethered capture needs the gphoto2 Python module, which isn't installed. "
                    "Install it with `pip install 'nlb[camera]'` (needs libgphoto2), "
                    "or run nlb inside `nix develop`. Review and rendering still work.")
        return f"Tethered capture needs libgphoto2, which failed to load: {e}"
    return None


class GPhotoBackend:
    def __init__(self):
        import gphoto2 as gp  # optional dependency; only needed with a real camera
        self.gp = gp
        self.cam = None

    @staticmethod
    def detect() -> bool:
        """Is a camera plugged in? Cheap (~50 ms); doesn't open it."""
        import gphoto2 as gp
        return len(gp.Camera.autodetect()) > 0

    def open(self) -> dict:
        gp = self.gp
        self.cam = gp.Camera()
        self.cam.init()
        warnings = []
        for name, value in REQUIRED_CONFIG:
            try:
                self.set_config(name, value)
            except gp.GPhoto2Error as e:
                warnings.append(f"could not set {name}={value}: {e}")
        return {"model": self.cam.get_abilities().model, "warnings": warnings}

    def close(self) -> None:
        if self.cam is not None:
            try:
                self.cam.exit()
            finally:
                self.cam = None

    def get_config(self) -> dict:
        gp, out = self.gp, {}
        for name in CONFIG_KEYS:
            try:
                w = self.cam.get_single_config(name)
            except gp.GPhoto2Error:
                continue
            is_choice = w.get_type() in (gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU)
            if is_choice and w.count_choices() == 0:
                # e.g. f-number with a manual lens: the value is NULL and
                # python-gphoto2 segfaults reading it
                continue
            choices = [w.get_choice(i) for i in range(w.count_choices())] if is_choice else []
            out[name] = {"label": w.get_label(), "value": w.get_value(), "choices": choices,
                         "readonly": bool(w.get_readonly())}
        return out

    def set_config(self, name: str, value: str) -> None:
        w = self.cam.get_single_config(name)
        w.set_value(value)
        self.cam.set_single_config(name, w)

    def preview(self) -> bytes:
        return bytes(memoryview(self.cam.capture_preview().get_data_and_size()))

    def capture(self, tmp: Path) -> list[Path]:
        path = self.cam.capture(self.gp.GP_CAPTURE_IMAGE)
        files = [self._download(path.folder, path.name, tmp)]
        # with RAW+JPEG the second file arrives as an event
        return files + self.poll(tmp, 1500)

    def poll(self, tmp: Path, timeout_ms: int) -> list[Path]:
        """Download files the camera announces (shutter pressed on the body)."""
        gp, files = self.gp, []
        typ, data = self.cam.wait_for_event(timeout_ms)
        while typ != gp.GP_EVENT_TIMEOUT:
            if typ == gp.GP_EVENT_FILE_ADDED:
                files.append(self._download(data.folder, data.name, tmp))
            typ, data = self.cam.wait_for_event(10)
        return files

    def _download(self, folder: str, name: str, tmp: Path) -> Path:
        dest = tmp / f"{time.monotonic_ns()}-{name}"
        self.cam.file_get(folder, name, self.gp.GP_FILE_TYPE_NORMAL).save(str(dest))
        try:  # like `gphoto2 --capture-image-and-download`: free the camera's RAM copy
            self.cam.file_delete(folder, name)
        except self.gp.GPhoto2Error:
            pass
        return dest


class FakeBackend:
    """Replays the raw files in `source` as captures; live view shows their embedded JPEGs."""

    def __init__(self, source: Path):
        self.files = sorted(p for p in source.iterdir() if p.suffix.lower() in RAW_SUFFIXES)
        if not self.files:
            raise ValueError(f"no raw files in {source} to fake captures with")
        self.next = itertools.cycle(self.files)
        self.config = {
            "iso": {"label": "ISO", "value": "100", "choices": ["100", "200", "400", "800"], "readonly": False},
            "shutterspeed": {"label": "Shutter Speed", "value": "1/15",
                             "choices": ["1/4", "1/8", "1/15", "1/30", "1/60"], "readonly": False},
            "imagequality": {"label": "Image Quality", "value": "RAW", "choices": ["RAW"], "readonly": False},
        }
        self.thumbs = {}
        self.current = self.files[0]

    def open(self) -> dict:
        return {"model": f"Fake camera ({len(self.files)} files)", "warnings": []}

    def close(self) -> None:
        pass

    def get_config(self) -> dict:
        return {k: dict(v) for k, v in self.config.items()}

    def set_config(self, name: str, value: str) -> None:
        if value not in self.config[name]["choices"]:
            raise ValueError(f"{value!r} is not a choice for {name}")
        self.config[name]["value"] = value

    def preview(self) -> bytes:
        time.sleep(0.1)
        if self.current not in self.thumbs:
            with rawpy.imread(str(self.current)) as raw:
                self.thumbs[self.current] = raw.extract_thumb().data
        return self.thumbs[self.current]

    def capture(self, tmp: Path) -> list[Path]:
        src = next(self.next)
        self.current = src
        dest = tmp / f"{time.monotonic_ns()}-{src.name}"
        shutil.copyfile(src, dest)
        return [dest]

    def poll(self, tmp: Path, timeout_ms: int) -> list[Path]:
        time.sleep(timeout_ms / 1000)
        return []


class CameraWorker(threading.Thread):
    """Serialises every camera call. `on_files(paths)` gets each batch of downloaded files."""

    def __init__(self, make_backend, tmp: Path, on_files, detect=None,
                 unavailable: str | None = None):
        """`detect()` says whether a camera is plugged in (None: assume one is). With
        `unavailable` set (the reason) the worker never touches a camera."""
        super().__init__(daemon=True, name="camera")
        self.make_backend, self.tmp, self.on_files = make_backend, tmp, on_files
        self.detect, self.unavailable = detect, unavailable
        self.auto_connect = True  # connect when a camera is plugged in
        self.present = None               # last detect() result
        self.next_detect = 0.0
        self.backend = None
        self.commands: queue.Queue = queue.Queue()
        self.state = {"status": "unavailable" if unavailable else "disconnected", "model": None,
                      "message": unavailable or "", "config": {}, "busy": False}
        self.state_lock = threading.Lock()
        self.frame = None           # latest live-view JPEG
        self.frame_seq = 0
        self.frame_cond = threading.Condition()
        self.viewers = 0

    # --- called from HTTP threads ---

    def snapshot(self) -> dict:
        with self.state_lock:
            return {**self.state, "liveview": self.viewers > 0}

    def submit(self, cmd: str, *args) -> Future:
        fut: Future = Future()
        self.commands.put((cmd, args, fut))
        return fut

    def add_viewer(self, delta: int) -> None:
        with self.frame_cond:
            self.viewers = max(0, self.viewers + delta)

    def wait_frame(self, after: int, timeout: float = 5.0) -> tuple[int, bytes | None]:
        with self.frame_cond:
            self.frame_cond.wait_for(lambda: self.frame_seq != after, timeout)
            return self.frame_seq, self.frame

    # --- worker ---

    def run(self) -> None:
        self.tmp.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                cmd, args, fut = self.commands.get(timeout=0 if self._streaming() else 0.05)
            except queue.Empty:
                self._idle()
                continue
            self._set(busy=True)
            try:
                fut.set_result(getattr(self, f"_cmd_{cmd}")(*args))
            except Exception as e:
                if cmd == "connect":  # expected (no camera, ...); the UI shows why
                    print(f"nlb studio: camera: {e}", flush=True)
                else:
                    traceback.print_exc()
                fut.set_exception(e)
                if self.backend is not None and cmd in ("capture", "connect"):
                    self._set(message=str(e))
            finally:
                self._set(busy=False)

    def _streaming(self) -> bool:
        return self.backend is not None and self.viewers > 0

    def _idle(self) -> None:
        if self.backend is None:
            self._watch()
            return
        try:
            if self._streaming():
                jpeg = self.backend.preview()
                with self.frame_cond:
                    self.frame, self.frame_seq = jpeg, self.frame_seq + 1
                    self.frame_cond.notify_all()
                files = self.backend.poll(self.tmp, 1)
            else:
                files = self.backend.poll(self.tmp, 200)
            if files:
                self.on_files(files)
        except Exception as e:  # unplugged, camera asleep, ...
            traceback.print_exc()
            self._drop(f"camera lost: {e}")

    def _watch(self) -> None:
        """Not connected: notice a camera being plugged in or out."""
        if self.unavailable or self.detect is None or time.monotonic() < self.next_detect:
            return
        self.next_detect = time.monotonic() + DETECT_EVERY
        try:
            present = self.detect()
        except Exception:
            traceback.print_exc()
            return
        was, self.present = self.present, present
        status = self.snapshot()["status"]
        if not present:
            if status != "nocamera":
                self._set(status="nocamera", message=NO_CAMERA)
        elif was is False and self.auto_connect:
            try:
                self._cmd_connect()
            except Exception as e:
                print(f"nlb studio: camera: {e}", flush=True)
        elif status == "nocamera":
            self._set(status="disconnected", message="")

    def _cmd_connect(self) -> dict:
        if self.unavailable:
            raise RuntimeError(self.unavailable)
        if self.backend is not None:
            return self.snapshot()
        self.auto_connect = True
        self._set(status="connecting", message="")
        backend = None
        try:
            backend = self.make_backend()
            info = backend.open()
            config = backend.get_config()
        except Exception as e:
            if backend is not None:
                backend.close()
            status, message = connect_hint(str(e))
            if status == "nocamera":
                self.present = False  # so plugging one in connects
            self._set(status=status, message=message)
            raise RuntimeError(message) from e
        self.backend, self.present = backend, True
        self._set(status="ready", model=info["model"], config=config,
                  message="; ".join(info["warnings"]))
        return self.snapshot()

    def _cmd_disconnect(self) -> dict:
        self.auto_connect = False  # leave the camera alone until asked again
        self._drop("")
        return self.snapshot()

    def _cmd_set_config(self, name: str, value: str) -> dict:
        self._require()
        self.backend.set_config(name, value)
        self._set(config=self.backend.get_config())
        return self.snapshot()

    def _cmd_capture(self) -> list[Path]:
        self._require()
        self._set(status="capturing")
        try:
            return self.backend.capture(self.tmp)
        finally:
            if self.backend is not None:
                self._set(status="ready")

    def _require(self) -> None:
        if self.backend is None:
            raise RuntimeError("camera not connected")

    def _drop(self, message: str) -> None:
        if self.backend is not None:
            try:
                self.backend.close()
            except Exception:
                pass
        self.backend = None
        self._set(status="disconnected" if not message else "error", model=None, config={},
                  message=message)

    def _set(self, **kw) -> None:
        with self.state_lock:
            self.state.update(kw)


def connect_hint(err: str) -> tuple[str, str]:
    """(status, message) for a failed connect."""
    if "-105" in err or "Unknown model" in err:
        return "nocamera", NO_CAMERA
    if "-53" in err or "busy" in err.lower():
        return "error", f"{err} - another program has the camera; try `gio mount -s gphoto2`."
    return "error", err
