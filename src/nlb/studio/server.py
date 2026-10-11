"""`nlb studio`: local web app for tethered capture, review and rendering of a roll."""
import json
import re
import threading
import traceback
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nlb import darktable, develop
from nlb.heic import RAW_SUFFIXES
from nlb.studio.cache import LRU, DarktablePreviews, Previews, edit_hash, to_jpeg
from nlb.studio.camera import CameraWorker, FakeBackend, GPhotoBackend, gphoto_missing
from nlb.studio.roll import Roll

STATIC = Path(__file__).parent / "static"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
VIEWS = ("crop", "full", "negative")


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
                    frame["crop"] = develop.auto_crop(lin, settings)
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
        names = self.roll_names()
        self.open_roll(roll or (max(names, key=lambda n: (self.library / n).stat().st_mtime)
                                if names else "roll01"), create=True)
        incoming = self.library / ".nlb" / "incoming"
        if fake_camera:
            self.camera = CameraWorker(lambda: FakeBackend(fake_camera), incoming, self.ingest)
        else:
            self.camera = CameraWorker(GPhotoBackend, incoming, self.ingest,
                                       detect=GPhotoBackend.detect, unavailable=gphoto_missing())
        self.camera.start()

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
                crop = develop.auto_crop(lin, roll.snapshot()["settings"])
                roll.update_frame(name, {"crop": crop})
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
                roll.update_frame(name, {k: template[k] for k in ("rotation", "angle", "params", "engine")
                                         if k in template})
        self.pool.submit(self.prepare, roll, name)
        return name

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
                "job": self.job.snapshot()}

    # --- roll-level actions ---

    def set_settings(self, patch: dict) -> None:
        roll = self.roll
        old = roll.snapshot()["settings"]
        roll.update_settings(patch)
        if "flip" in patch and bool(patch["flip"]) != bool(old.get("flip")):
            # crops live in full-view space, which just got mirrored
            for name, frame in roll.snapshot()["frames"].items():
                if frame.get("crop"):
                    x, y, w, h = frame["crop"]
                    roll.update_frame(name, {"crop": [1.0 - x - w, y, w, h]})

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

    @route("GET", r"/api/camera/live")
    def camera_live(h, body, q):
        h.stream_mjpeg(studio.camera)

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
