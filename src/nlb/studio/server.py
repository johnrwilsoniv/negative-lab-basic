"""`nlb studio`: local web app for tethered capture, review and rendering of a roll."""
import json
import re
import shutil
import threading
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from nlb import darktable, develop
from nlb.heic import RAW_SUFFIXES
from nlb.studio import feedback, focus
from nlb.studio.cache import LRU, DarktablePreviews, Previews, edit_hash, to_jpeg
from nlb.studio.camera import CameraWorker, FakeBackend, GPhotoBackend, gphoto_missing
from nlb.studio.roll import Roll

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
VIEWS = ("crop", "full", "negative")
TEST_VIEWS = ("frame", "result", "sensor")
SHOOT_MODES = ("test", "direct")
TEMPLATE_KEYS = ("rotation", "angle", "params", "engine")


class RenderJob:
    """Full-resolution 16-bit TIFFs for the kept frames, one at a time, in the background."""

    def __init__(self):
        self.lock = threading.Lock()
        self.state = {"running": False, "done": 0, "total": 0, "current": None, "errors": [],
                      "out": None}

    def snapshot(self) -> dict:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, roll: Roll, names: list[str], out: Path) -> bool:
        with self.lock:
            if self.state["running"]:
                return False
            self.state = {"running": True, "done": 0, "total": len(names), "current": None,
                          "errors": [], "out": str(out)}
        threading.Thread(target=self._run, args=(roll, names, out), daemon=True).start()
        return True

    def _run(self, roll: Roll, names: list[str], out: Path) -> None:
        out.mkdir(parents=True, exist_ok=True)
        for name in names:
            with self.lock:
                self.state["current"] = name
            try:
                snap = roll.snapshot()
                settings, frame, path = snap["settings"], snap["frames"][name], roll.path(name)
                lin = None
                if frame.get("crop") is None or frame.get("engine") != "darktable":
                    lin = develop.load_linear(path, preview=False)
                if frame.get("crop") is None:
                    frame.update(develop.auto_frame(lin, settings))
                if frame.get("engine") == "darktable":
                    positive = darktable.render(path, settings["film"], darktable.sensor_shape(path),
                                                base=settings.get("base"))
                    img = develop.place(positive, settings, frame, view="crop")
                    del positive
                else:
                    img = develop.develop(lin, settings, frame, view="crop")
                del lin
                develop.write_tiff(out / f"{name}.tif", img)
            except Exception as e:
                traceback.print_exc()
                with self.lock:
                    self.state["errors"].append(f"{name}: {e}")
            with self.lock:
                self.state["done"] += 1
        with self.lock:
            self.state["running"] = False
            self.state["current"] = None


ROLL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


def out_dir(roll: Roll) -> Path:
    return roll.folder.parent / f"{roll.folder.name}-positive"


def is_roll_dir(path: Path) -> bool:
    """A folder that is a roll itself (has roll.json or raw files), not a library of rolls."""
    return (path / "roll.json").exists() or any(
        p.is_file() and p.suffix.lower() in RAW_SUFFIXES for p in path.iterdir())


class Studio:
    """A library folder whose subfolders are rolls; one roll is current at a time."""

    def __init__(self, library: Path, roll: str | None = None, prefix: str = "frame",
                 fake_camera: Path | None = None):
        self.library = library.resolve()
        self.library.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.rolls: dict[str, Roll] = {}
        self.rolls_lock = threading.Lock()
        self.previews = Previews()
        self.darktable = DarktablePreviews(self.previews)
        self.jpegs = LRU(300)
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="prepare")
        self.job = RenderJob()
        self.ingest_lock = threading.Lock()
        self.shoot_mode = "test"   # where captures go: the test-shot slot, or straight into the roll
        self.test_dir = self.library / ".nlb" / "test"
        self.test: dict | None = None
        self.test_seq = 0
        self.test_lock = threading.Lock()
        self.test_history: list[dict] = []  # {"id", "headroom", "edge_px"}, for focus comparisons
        self.focus_cache = None  # ((frame seq, region), score): several viewers poll the same frame
        names = self.roll_names()
        self.open_roll(roll or (max(names, key=lambda n: (self.library / n).stat().st_mtime)
                                if names else "roll01"), create=True)
        incoming = self.library / ".nlb" / "incoming"
        if fake_camera:
            self.camera = CameraWorker(lambda: FakeBackend(fake_camera), incoming, self.camera_files)
        else:
            self.camera = CameraWorker(GPhotoBackend, incoming, self.camera_files,
                                       detect=GPhotoBackend.detect, unavailable=gphoto_missing())
        self.camera.start()
        self.restore_test()

    # --- rolls ---

    def roll_names(self) -> list[str]:
        return sorted(p.name for p in self.library.iterdir()
                      if p.is_dir() and not p.name.startswith(".") and not p.name.endswith("-positive"))

    def get_roll(self, name: str | None, create: bool = False) -> Roll:
        if name is None:
            return self.roll
        if not ROLL_NAME.match(name) or name.endswith("-positive"):
            raise ValueError(f"bad roll name {name!r}")
        with self.rolls_lock:
            if name not in self.rolls:
                if not create and name not in self.roll_names():
                    raise KeyError(f"no roll {name!r}")
                self.rolls[name] = Roll(self.library / name, prefix=self.prefix)
            return self.rolls[name]

    def open_roll(self, name: str, create: bool = False) -> Roll:
        roll = self.get_roll(name, create=create)
        self.roll = roll
        self.prepare_missing(roll)
        return roll

    def prepare_missing(self, roll: Roll) -> None:
        for name, frame in roll.snapshot()["frames"].items():
            if frame.get("crop") is None:
                self.pool.submit(self.prepare, roll, name)

    # --- frames ---

    def prepare(self, roll: Roll, name: str) -> None:
        """Decode the preview and set the initial crop, so the first view is instant."""
        try:
            with roll.lock:
                if name not in roll.frames:
                    return
                path = roll.path(name)
            lin = self.previews.linear(path)
            if roll.frames.get(name, {}).get("crop") is None:
                roll.update_frame(name, develop.auto_frame(lin, roll.snapshot()["settings"]))
        except Exception:
            traceback.print_exc()

    def ingest(self, files: list[Path], reshoot: str | None = None) -> str:
        """Files fresh off the camera become one frame (RAW+JPEG share a name) in the current roll."""
        roll = self.roll
        with self.ingest_lock:
            snap = roll.snapshot()["frames"]
            if reshoot and reshoot in snap:
                name, template = reshoot, snap[reshoot]
                roll.discard(reshoot)
            else:
                name = roll.next_name()
                template = snap[list(snap)[-1]] if snap else None
            for f in files:
                roll.add_capture(f, name)
            if name in roll.frames and template:
                # same holder, same film: carry orientation and adjustments over
                roll.update_frame(name, {k: template[k] for k in TEMPLATE_KEYS if k in template})
        self.pool.submit(self.prepare, roll, name)
        return name

    def camera_files(self, files: list[Path]) -> None:
        """Files from the camera's own shutter button follow the shoot mode, like Space does."""
        if self.shoot_mode == "test":
            self.new_test(files)
        else:
            self.ingest(files)

    # --- test shots: shoot, get feedback, then keep into the roll or throw away ---

    def new_test(self, files: list[Path], config: dict | None = None) -> int:
        """`files` (one capture) become the test shot, replacing (deleting) the previous one."""
        with self.test_lock:
            self.test_seq += 1
            tid = self.test_seq
            dest = self.test_dir / f"{tid:04d}"
            dest.mkdir(parents=True, exist_ok=True)
            moved = []
            for f in files:
                shutil.move(f, dest / f.name)
                moved.append(dest / f.name)
            old, self.test = self.test, {
                "id": tid, "dir": dest, "files": moved, "status": "analyzing", "error": None,
                "config": config if config is not None else self.camera.snapshot()["config"],
                "report": None, "metrics": None, "crop": None}
        if old:
            shutil.rmtree(old["dir"], ignore_errors=True)
        self.pool.submit(self.analyze_test, tid)
        return tid

    def restore_test(self) -> None:
        """A test shot left over from the last session comes back; older ones are deleted."""
        if not self.test_dir.is_dir():
            return
        dirs = sorted(d for d in self.test_dir.iterdir() if d.is_dir())
        for d in dirs[:-1]:
            shutil.rmtree(d, ignore_errors=True)
        if dirs and (files := sorted(p for p in dirs[-1].iterdir() if p.is_file())):
            self.test_seq = int(dirs[-1].name) if dirs[-1].name.isdigit() else 0
            tmp = self.test_dir / ".restore"
            shutil.rmtree(tmp, ignore_errors=True)
            dirs[-1].rename(tmp)
            self.new_test(sorted(tmp.iterdir()), config={})
            shutil.rmtree(tmp, ignore_errors=True)

    def _test(self, tid: int | None = None) -> dict:
        t = self.test
        if t is None or (tid is not None and t["id"] != tid):
            raise KeyError("no such test shot" if t else "no test shot")
        return t

    @staticmethod
    def _raw(t: dict) -> Path:
        raw = next((f for f in t["files"] if f.suffix.lower() in RAW_SUFFIXES), None)
        if raw is None:
            got = ", ".join(f.suffix.lstrip(".").upper() for f in t["files"]) or "nothing"
            raise ValueError(f"the camera sent {got}, not a raw file: set Image Quality to RAW "
                             "and PC Save Image Size to Original")
        return raw

    def analyze_test(self, tid: int) -> None:
        t = self.test
        if t is None or t["id"] != tid:
            return  # replaced, kept or thrown away before we got to it
        try:
            raw = self._raw(t)
            roll = self.roll
            snap = roll.snapshot()
            settings = snap["settings"]
            half = develop.load_linear(raw, preview=True)
            lin = self.previews.seed(raw, half)
            metrics = develop.capture_metrics(lin, settings, detail=half)
            del half
            crop = develop.auto_crop(lin, settings)
            best = self._sharpest(metrics)
            report = feedback.assess(metrics, t["config"], self._reference(roll, snap), best, scale=2.0)
            self.test_history.append({"id": tid, "headroom": metrics["base_headroom"],
                                      "edge_px": metrics["edge_px"]})
            update = {"status": "ready", "report": report, "metrics": metrics, "crop": crop}
        except Exception as e:
            traceback.print_exc()
            update = {"status": "error", "error": str(e)}
        with self.test_lock:
            if self.test and self.test["id"] == tid:
                self.test.update(update)

    def _sharpest(self, metrics: dict) -> dict | None:
        """The sharpest earlier test shot at about this exposure (clipped holes read sharper)."""
        if metrics.get("edge_px") is None:
            return None
        h = max(metrics["base_headroom"], 1e-4)
        same = [t for t in self.test_history if t["edge_px"] is not None
                and abs(np.log2(max(t["headroom"], 1e-4) / h)) <= feedback.SAME_EXPOSURE]
        return min(same, key=lambda t: t["edge_px"], default=None)

    def _reference(self, roll: Roll, snap: dict) -> dict | None:
        """What the shot should match: the roll's picked film base, else its last kept frame."""
        if snap["settings"].get("base"):
            return {"label": "the roll's film base", "base": snap["settings"]["base"]}
        kept = [n for n, f in snap["frames"].items() if not f.get("rejected")]
        if not kept:
            return None
        try:
            lin = self.previews.linear(roll.path(kept[-1]))
            base = develop.exposure_report(lin, {**snap["settings"], "base": None})["base"]
        except Exception:
            traceback.print_exc()
            return None
        return {"label": kept[-1], "base": base}

    def _test_frame(self, t: dict, snap: dict) -> dict:
        frames = snap["frames"]
        template = frames[list(frames)[-1]] if frames else {}
        return {**{k: template[k] for k in ("rotation", "params") if k in template},
                "angle": 0.0, "crop": t["crop"] or develop.FALLBACK_CROP}

    def test_image(self, tid: int, view: str) -> bytes:
        t = self._test(tid)
        raw = self._raw(t)
        snap = self.roll.snapshot()
        settings, frame = snap["settings"], self._test_frame(t, snap)
        if view == "frame":
            # sensor orientation, own film base: the frame as live view shows it
            settings = {**settings, "flip": False, "base": None}
            frame = {**frame, "rotation": 0, "crop": (t["metrics"] or {}).get("picture") or develop.FALLBACK_CROP}
        key = ("test", tid, view, edit_hash(settings, frame))
        jpeg = self.jpegs.get(key)
        if jpeg is None:
            lin = self.previews.linear(raw)
            if view == "sensor":
                img = sensor_map(lin)
            else:
                img = develop.develop(lin, settings, frame, view="full" if view == "frame" else "crop")
            jpeg = to_jpeg(img, quality=88)
            self.jpegs.put(key, jpeg)
        return jpeg

    def keep_test(self, reshoot: str | None = None) -> str:
        """The test shot joins the current roll as its next frame (or replaces `reshoot`)."""
        with self.test_lock:
            t = self._test()
            self._raw(t)
            self.test = None
        try:
            name = self.ingest(t["files"], reshoot)
        except Exception:
            with self.test_lock:
                self.test = self.test or t  # nothing lost: still the test shot
            raise
        shutil.rmtree(t["dir"], ignore_errors=True)
        if t["crop"] and name in self.roll.frames and self.roll.frames[name].get("crop") is None:
            self.roll.update_frame(name, {"crop": t["crop"]})
        return name

    def discard_test(self) -> None:
        with self.test_lock:
            t, self.test = self.test, None
        if t:
            shutil.rmtree(t["dir"], ignore_errors=True)

    def set_shoot_mode(self, mode: str) -> None:
        if mode not in SHOOT_MODES:
            raise ValueError(f"mode must be one of {SHOOT_MODES}")
        self.shoot_mode = mode

    def test_state(self) -> dict | None:
        t = self.test
        if t is None:
            return None
        return {"id": t["id"], "status": t["status"], "error": t["error"], "report": t["report"],
                "metrics": t["metrics"], "files": [f.name for f in t["files"]],
                "settings": feedback.describe_settings(t["config"])}

    def image(self, roll: Roll, name: str, view: str, thumb: bool) -> tuple[bytes, str]:
        snap = roll.snapshot()
        frame = snap["frames"][name]
        if frame.get("crop") is None:
            self.prepare(roll, name)
            snap = roll.snapshot()
            frame = snap["frames"][name]
        h = edit_hash(snap["settings"], frame)
        key = (str(roll.folder), name, view, thumb, h)
        jpeg = self.jpegs.get(key)
        if jpeg is None:
            path = roll.path(name)
            if frame.get("engine") == "darktable" and view != "negative":
                positive = self.darktable.positive(path, snap["settings"]["film"], snap["settings"].get("base"),
                                                   thumb=thumb)
                img = develop.place(positive, snap["settings"], frame, view=view)
            else:
                img = develop.develop(self.previews.linear(path, thumb=thumb), snap["settings"], frame,
                                      view=view)
            jpeg = to_jpeg(img, quality=80 if thumb else 90)
            self.jpegs.put(key, jpeg)
        return jpeg, h

    def state(self) -> dict:
        roll = self.roll
        if roll.scan():  # files added or removed by hand
            self.prepare_missing(roll)
        snap = roll.snapshot()
        frames = [{"name": n, **f, "hash": edit_hash(snap["settings"], f)}
                  for n, f in snap["frames"].items()]
        return {"version": roll.version, "library": str(self.library), "roll": roll.folder.name,
                "rolls": self.roll_names(), "folder": str(roll.folder), "out": str(out_dir(roll)),
                "settings": snap["settings"], "frames": frames, "params": develop.PARAMS,
                "next_name": roll.next_name(), "camera": self.camera.snapshot(),
                "darktable": darktable.status(),
                "job": self.job.snapshot(), "shoot_mode": self.shoot_mode, "test": self.test_state()}

    # --- live view focus meter ---

    def live_focus(self, region: tuple[float, float, float, float]) -> dict:
        """Sharpness of the latest live-view frame within `region`; `seq` says which frame."""
        seq, jpeg = self.camera.latest()
        key = (seq, region)
        cached = self.focus_cache
        if cached is None or cached[0] != key:
            cached = self.focus_cache = (key, focus.sharpness(jpeg, region) if jpeg else None)
        return {"seq": seq, "score": cached[1]}

    # --- roll-level actions ---

    def set_settings(self, patch: dict) -> None:
        roll = self.roll
        old = roll.snapshot()["settings"]
        roll.update_settings(patch)
        if "flip" in patch and bool(patch["flip"]) != bool(old.get("flip")):
            # crops live in full-view space, which just got mirrored; so did the deskew
            for name, frame in roll.snapshot()["frames"].items():
                patch = {"angle": -float(frame.get("angle") or 0.0)}
                if frame.get("crop"):
                    x, y, w, h = frame["crop"]
                    patch["crop"] = [1.0 - x - w, y, w, h]
                roll.update_frame(name, patch)

    def pick_base(self, name: str, x: float, y: float) -> list[float]:
        roll = self.roll
        snap = roll.snapshot()
        lin = self.previews.linear(roll.path(name))
        base = develop.sample_base(lin, snap["settings"], snap["frames"][name], x, y)
        roll.update_settings({"base": base})
        return base

    def lock_levels(self, lock: bool) -> None:
        roll = self.roll
        if not lock:
            roll.update_settings({"levels": None})
            return
        snap = roll.snapshot()
        settings = {**snap["settings"], "levels": None}
        samples = [(self.previews.linear(roll.path(n)), f) for n, f in snap["frames"].items()
                   if not f.get("rejected") and f.get("crop")]
        roll.update_settings({"levels": develop.analyze_roll(samples, settings)})

    def render(self, names: list[str] | None) -> bool:
        roll = self.roll
        frames = roll.snapshot()["frames"]
        names = [n for n in (names or frames) if n in frames and not frames[n].get("rejected")]
        return self.job.start(roll, names, out_dir(roll))


def sensor_map(lin: np.ndarray) -> np.ndarray:
    """What the sensor recorded: brightest channel in gray (display gamma), clipped pixels red."""
    peak = lin.max(axis=2)
    gray = np.power(np.clip(peak, 0.0, 1.0), 1 / 2.2)
    img = np.repeat(gray[..., None], 3, axis=2)
    img[peak >= 0.98] = (1.0, 0.15, 0.1)
    return img


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_handler(studio: Studio):
    routes = []

    def route(method: str, pattern: str):
        def deco(fn):
            routes.append((method, re.compile(f"^{pattern}$"), fn))
            return fn
        return deco

    def frame_name(name: str) -> str:
        if name not in studio.roll.frames:
            raise ApiError(404, f"no frame {name!r}")
        return name

    @route("GET", r"/api/state")
    def get_state(h, body, q):
        return studio.state()

    @route("POST", r"/api/rolls")
    def create_roll(h, body, q):
        name = str(body.get("name", "")).strip()
        if name in studio.roll_names():
            raise ApiError(409, f"roll {name!r} already exists")
        studio.open_roll(name, create=True)
        return studio.state()

    @route("POST", r"/api/rolls/open")
    def open_roll(h, body, q):
        try:
            studio.open_roll(str(body.get("name", "")))
        except KeyError as e:
            raise ApiError(404, str(e))
        return studio.state()

    @route("PATCH", r"/api/settings")
    def patch_settings(h, body, q):
        studio.set_settings(body)
        return studio.state()

    @route("PATCH", r"/api/frames/(?P<name>[^/]+)")
    def patch_frame(h, body, q, name):
        return studio.roll.update_frame(frame_name(name), body)

    @route("POST", r"/api/frames/(?P<name>[^/]+)/discard")
    def discard_frame(h, body, q, name):
        studio.roll.discard(frame_name(name))
        return {"ok": True}

    @route("GET", r"/api/frames/(?P<name>[^/]+)/image")
    def frame_image(h, body, q, name):
        view = q.get("view", "crop")
        if view not in VIEWS:
            raise ApiError(400, f"view must be one of {VIEWS}")
        try:  # the URL names its roll, so images requested just before a roll switch still resolve
            roll = studio.get_roll(q.get("roll"))
        except (KeyError, ValueError) as e:
            raise ApiError(404, str(e))
        if name not in roll.frames:
            raise ApiError(404, f"no frame {name!r}")
        jpeg, digest = studio.image(roll, name, view, q.get("size") == "thumb")
        # URLs carry the edit hash, so a matching hash can be cached forever
        cache = "public, max-age=31536000, immutable" if q.get("h") == digest else "no-cache"
        h.send_bytes(jpeg, "image/jpeg", cache)

    @route("POST", r"/api/base")
    def post_base(h, body, q):
        if body.get("auto"):
            studio.roll.update_settings({"base": None})
            return {"base": None}
        return {"base": studio.pick_base(frame_name(body["name"]), float(body["x"]), float(body["y"]))}

    @route("POST", r"/api/levels")
    def post_levels(h, body, q):
        studio.lock_levels(bool(body.get("lock")))
        return studio.state()

    @route("POST", r"/api/render")
    def post_render(h, body, q):
        if not studio.render(body.get("names")):
            raise ApiError(409, "a render is already running")
        return studio.job.snapshot()

    @route("POST", r"/api/camera/(?P<action>connect|disconnect)")
    def camera_conn(h, body, q, action):
        try:
            return studio.camera.submit(action).result(timeout=60)
        except Exception as e:
            raise ApiError(502, str(e))

    @route("POST", r"/api/camera/config")
    def camera_config(h, body, q):
        try:
            return studio.camera.submit("set_config", body["name"], str(body["value"])).result(timeout=30)
        except Exception as e:
            raise ApiError(502, str(e))

    @route("POST", r"/api/camera/capture")
    def camera_capture(h, body, q):
        reshoot = body.get("reshoot")
        if reshoot:
            frame_name(reshoot)
        try:
            files = studio.camera.submit("capture").result(timeout=120)
        except Exception as e:
            raise ApiError(502, str(e))
        if not files:
            raise ApiError(502, "camera returned no file")
        return {"name": studio.ingest(files, reshoot)}

    @route("POST", r"/api/test/capture")
    def test_capture(h, body, q):
        try:
            files = studio.camera.submit("capture").result(timeout=120)
        except Exception as e:
            raise ApiError(502, str(e))
        if not files:
            raise ApiError(502, "camera returned no file")
        return {"id": studio.new_test(files)}

    @route("POST", r"/api/test/keep")
    def test_keep(h, body, q):
        reshoot = body.get("reshoot")
        if reshoot:
            frame_name(reshoot)
        try:
            return {"name": studio.keep_test(reshoot)}
        except KeyError as e:
            raise ApiError(404, str(e))

    @route("POST", r"/api/test/discard")
    def test_discard(h, body, q):
        studio.discard_test()
        return {"ok": True}

    @route("POST", r"/api/test/mode")
    def test_mode(h, body, q):
        studio.set_shoot_mode(str(body.get("mode")))
        return studio.state()

    @route("GET", r"/api/test/image")
    def test_image(h, body, q):
        view = q.get("view", "frame")
        if view not in TEST_VIEWS:
            raise ApiError(400, f"view must be one of {TEST_VIEWS}")
        try:
            jpeg = studio.test_image(int(q.get("id", 0)), view)
        except KeyError as e:
            raise ApiError(404, str(e))
        h.send_bytes(jpeg, "image/jpeg", "no-cache")

    @route("GET", r"/api/camera/live")
    def camera_live(h, body, q):
        h.stream_mjpeg(studio.camera)

    @route("GET", r"/api/camera/focus")
    def camera_focus(h, body, q):
        try:
            region = tuple(float(q.get(k, d)) for k, d in (("x", 0), ("y", 0), ("w", 1), ("h", 1)))
        except ValueError:
            raise ApiError(400, "x, y, w, h must be numbers")
        return studio.live_focus(region)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet; errors are printed where they happen
            pass

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def do_PATCH(self):
            self.dispatch("PATCH")

        def dispatch(self, method: str):
            url = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            try:
                if method == "GET" and not url.path.startswith("/api/"):
                    return self.static(url.path)
                for m, pat, fn in routes:
                    match = pat.match(url.path)
                    if m == method and match:
                        length = int(self.headers.get("Content-Length") or 0)
                        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                        result = fn(self, body, q, **match.groupdict())
                        if result is not None:
                            self.send_json(result)
                        return
                raise ApiError(404, f"no route {method} {url.path}")
            except ApiError as e:
                self.send_json({"error": str(e)}, e.status)
            except (ValueError, KeyError) as e:
                self.send_json({"error": str(e)}, 400)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                traceback.print_exc()
                self.send_json({"error": str(e)}, 500)

        def static(self, path: str):
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (STATIC / rel).resolve()
            if STATIC.resolve() not in target.parents or not target.is_file():
                raise ApiError(404, "not found")
            self.send_bytes(target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"),
                            "no-cache")

        def send_json(self, obj, status: int = 200):
            self.send_bytes(json.dumps(obj).encode(), "application/json", "no-store", status)

        def send_bytes(self, data: bytes, ctype: str, cache: str, status: int = 200):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(data)

        def stream_mjpeg(self, worker: CameraWorker):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            worker.add_viewer(1)
            try:
                seq = -1
                while True:
                    new, jpeg = worker.wait_frame(seq)
                    if new == seq:
                        continue
                    seq = new
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                worker.add_viewer(-1)

    return Handler


def serve(folder: Path, host: str = "127.0.0.1", port: int = 8765, prefix: str = "frame",
          fake_camera: Path | None = None, open_browser: bool = True, connect: bool = True) -> int:
    """`folder` is a library of roll subfolders, or one roll (then its parent is the library)."""
    folder = folder.resolve()
    if not folder.exists() or is_roll_dir(folder):
        studio = Studio(folder.parent, roll=folder.name, prefix=prefix, fake_camera=fake_camera)
    else:
        studio = Studio(folder, prefix=prefix, fake_camera=fake_camera)
    if studio.camera.unavailable:
        print(f"nlb studio: capture disabled. {studio.camera.unavailable}", flush=True)
    elif connect:
        studio.camera.submit("connect")  # failure just shows up as camera status in the UI
    server = ThreadingHTTPServer((host, port), make_handler(studio))
    server.daemon_threads = True
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"nlb studio: {studio.library} (roll {studio.roll.folder.name}) at {url}  (Ctrl-C to stop)",
          flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
