import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np
import pytest
from synth import make_negative, write_dng

from nlb import darktable
from nlb.studio import camera as camera_mod
from nlb.studio.camera import CameraWorker, FakeBackend
from nlb.studio.roll import Roll, clamp_crop
from nlb.studio.server import Studio, make_handler


def raw_folder(path, n=2):
    path.mkdir()
    for i in range(n):
        write_dng(path / f"SRC_{i:04d}.DNG", make_negative(seed=i))
    return path


# --- Roll ---

def test_new_roll_is_mirrored_by_default(tmp_path):
    assert Roll(tmp_path / "roll").settings["flip"] is True  # film is scanned backwards


def test_next_name_resumes_and_skips_trash(tmp_path):
    roll = Roll(tmp_path / "roll")
    assert roll.next_name() == "frame-001"
    (roll.folder / "frame-007.ARW").write_bytes(b"x")
    roll.trash.mkdir(parents=True)
    (roll.trash / "frame-009.20261010-120000.ARW").write_bytes(b"x")
    assert roll.next_name() == "frame-008"


def test_scan_picks_up_raws_only(tmp_path):
    folder = tmp_path / "roll"
    folder.mkdir()
    for name in ("A.ARW", "B.dng", "C.JPG", "._A.ARW", "roll.json.tmp"):
        (folder / name).write_bytes(b"x")
    roll = Roll(folder)
    assert list(roll.frames) == ["A", "B"]
    assert json.loads((folder / "roll.json").read_text())["frames"]["A"]["file"] == "A.ARW"
    (folder / "B.dng").unlink()
    assert roll.scan() and list(roll.frames) == ["A"]


def test_discard_moves_to_trash_and_keeps_others(tmp_path):
    folder = tmp_path / "roll"
    folder.mkdir()
    (folder / "frame-001.ARW").write_bytes(b"raw")
    (folder / "frame-001.JPG").write_bytes(b"jpg")
    (folder / "frame-0010.ARW").write_bytes(b"other")
    roll = Roll(folder)
    roll.discard("frame-001")
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == ["frame-0010.ARW", "roll.json"]
    assert len(list(roll.trash.iterdir())) == 2
    assert list(roll.frames) == ["frame-0010"]


def test_update_frame_validates(tmp_path):
    folder = tmp_path / "roll"
    folder.mkdir()
    (folder / "A.ARW").write_bytes(b"x")
    roll = Roll(folder)
    with pytest.raises(ValueError):
        roll.update_frame("A", {"rotation": 45})
    with pytest.raises(ValueError):
        roll.update_frame("A", {"bogus": 1})
    with pytest.raises(ValueError):
        roll.update_frame("A", {"engine": "lightroom"})
    f = roll.update_frame("A", {"angle": 12, "params": {"exposure": 0.5}})
    assert f["angle"] == 5.0
    f = roll.update_frame("A", {"params": {"contrast": 0.2}})
    assert f["params"] == {"exposure": 0.5, "contrast": 0.2}
    assert Roll(folder).frames["A"]["params"] == {"exposure": 0.5, "contrast": 0.2}  # persisted


def test_clamp_crop():
    assert clamp_crop([-0.1, 0.5, 2, 0.8]) == [0.0, 0.5, 1.0, 0.5]


# --- HTTP API, end to end with the fake camera ---

@pytest.fixture
def studio(tmp_path):
    source = raw_folder(tmp_path / "source")
    st = Studio(tmp_path, roll="roll", fake_camera=source)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(st))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    st.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield st
    server.shutdown()
    server.server_close()


def call(st, method, path, body=None):
    req = urllib.request.Request(st.base_url + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        data = res.read()
        return json.loads(data) if res.headers["Content-Type"] == "application/json" else data


def test_capture_review_render(studio):
    assert call(studio, "POST", "/api/camera/connect")["status"] == "ready"
    assert call(studio, "POST", "/api/camera/capture", {})["name"] == "frame-001"
    assert call(studio, "POST", "/api/camera/capture", {})["name"] == "frame-002"

    studio.pool.shutdown(wait=True)  # wait for previews and auto crops
    state = call(studio, "GET", "/api/state")
    assert [f["name"] for f in state["frames"]] == ["frame-001", "frame-002"]
    assert all(f["crop"] for f in state["frames"])
    assert state["next_name"] == "frame-003"
    assert {p["key"] for p in state["params"]} >= {"exposure"}

    for view in ("crop", "full", "negative"):
        jpeg = call(studio, "GET", f"/api/frames/frame-001/image?view={view}&size=thumb")
        assert jpeg[:2] == b"\xff\xd8"

    call(studio, "PATCH", "/api/frames/frame-001", {"rotation": 90, "params": {"exposure": 0.3}})
    call(studio, "PATCH", "/api/frames/frame-002", {"rejected": True})
    base = call(studio, "POST", "/api/base", {"name": "frame-001", "x": 0.5, "y": 0.5})["base"]
    assert len(base) == 3
    assert call(studio, "POST", "/api/levels", {"lock": True})["settings"]["levels"]

    call(studio, "POST", "/api/render", {})
    while call(studio, "GET", "/api/state")["job"]["running"]:
        pass
    job = call(studio, "GET", "/api/state")["job"]
    assert job["errors"] == [] and job["total"] == 1  # rejected frame skipped
    tif = studio.library / "roll-positive" / "frame-001.tif"
    import cv2
    img = cv2.imread(str(tif), cv2.IMREAD_UNCHANGED)
    assert img.dtype == np.uint16 and img.shape[0] > img.shape[1]  # rotated to portrait


def test_reshoot_keeps_name_and_edits(studio):
    call(studio, "POST", "/api/camera/connect")
    call(studio, "POST", "/api/camera/capture", {})
    call(studio, "PATCH", "/api/frames/frame-001", {"rotation": 180})
    assert call(studio, "POST", "/api/camera/capture", {"reshoot": "frame-001"})["name"] == "frame-001"
    state = call(studio, "GET", "/api/state")
    assert [f["name"] for f in state["frames"]] == ["frame-001"]
    assert state["frames"][0]["rotation"] == 180
    assert len(list(studio.roll.trash.iterdir())) == 1
    # a new frame inherits the previous frame's orientation
    call(studio, "POST", "/api/camera/capture", {})
    assert call(studio, "GET", "/api/state")["frames"][1]["rotation"] == 180


def test_rolls(studio, tmp_path):
    (tmp_path / "older").mkdir()
    write_dng(tmp_path / "older" / "A.DNG", make_negative())
    (tmp_path / "older-positive").mkdir()
    state = call(studio, "GET", "/api/state")
    assert state["roll"] == "roll" and state["rolls"] == ["older", "roll", "source"]

    state = call(studio, "POST", "/api/rolls/open", {"name": "older"})
    assert state["roll"] == "older" and [f["name"] for f in state["frames"]] == ["A"]
    assert call(studio, "GET", "/api/frames/A/image?size=thumb&roll=older")[:2] == b"\xff\xd8"

    state = call(studio, "POST", "/api/rolls", {"name": "roll02"})
    assert state["roll"] == "roll02" and state["frames"] == []
    assert (tmp_path / "roll02" / "roll.json").exists()
    call(studio, "POST", "/api/camera/connect")
    assert call(studio, "POST", "/api/camera/capture", {})["name"] == "frame-001"
    assert (tmp_path / "roll02" / "frame-001.DNG").exists()

    for bad in ({"name": "roll02"}, {"name": "../x"}, {"name": "x-positive"}):
        with pytest.raises(urllib.error.HTTPError):
            call(studio, "POST", "/api/rolls", bad)
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "POST", "/api/rolls/open", {"name": "nope"})
    assert e.value.code == 404


def test_errors(studio):
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "PATCH", "/api/frames/nope", {"rotation": 90})
    assert e.value.code == 404
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "POST", "/api/camera/capture", {})  # not connected yet
    assert e.value.code == 502
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "GET", "/../pyproject.toml")
    assert e.value.code == 404


# --- test shots ---

def wait_for(fn, timeout=30.0):
    import time
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if v := fn():
            return v
        time.sleep(0.05)
    raise AssertionError("timed out")


def test_shot_feedback_then_keep(studio):
    call(studio, "POST", "/api/camera/connect")
    assert call(studio, "GET", "/api/state")["shoot_mode"] == "test"
    tid = call(studio, "POST", "/api/test/capture", {})["id"]
    test = wait_for(lambda: (t := call(studio, "GET", "/api/state")["test"]) and t["status"] != "analyzing" and t)
    assert test["id"] == tid and test["status"] == "ready", test
    assert test["report"]["verdict"] in ("good", "adjust", "bad")
    assert {c["key"] for c in test["report"]["checks"]} >= {"settings"}
    assert test["settings"].startswith("ISO 100")
    assert call(studio, "GET", "/api/state")["frames"] == []  # nothing in the roll yet
    for view in ("frame", "result", "sensor"):
        assert call(studio, "GET", f"/api/test/image?id={tid}&view={view}")[:2] == b"\xff\xd8"

    # a second test shot replaces the first
    tid2 = call(studio, "POST", "/api/test/capture", {})["id"]
    assert tid2 == tid + 1
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "GET", f"/api/test/image?id={tid}&view=frame")
    assert e.value.code == 404
    assert [p.name for p in studio.test_dir.iterdir()] == [f"{tid2:04d}"]

    assert call(studio, "POST", "/api/test/keep", {})["name"] == "frame-001"
    state = call(studio, "GET", "/api/state")
    assert state["test"] is None and [f["name"] for f in state["frames"]] == ["frame-001"]
    assert (studio.roll.folder / "frame-001.DNG").exists()
    assert list(studio.test_dir.iterdir()) == []
    with pytest.raises(urllib.error.HTTPError) as e:
        call(studio, "POST", "/api/test/keep", {})
    assert e.value.code == 404

    # keep in place of the last frame
    call(studio, "POST", "/api/test/capture", {})
    assert call(studio, "POST", "/api/test/keep", {"reshoot": "frame-001"})["name"] == "frame-001"
    assert len(list(studio.roll.trash.iterdir())) == 1

    call(studio, "POST", "/api/test/capture", {})
    call(studio, "POST", "/api/test/discard", {})
    assert call(studio, "GET", "/api/state")["test"] is None
    assert list(studio.test_dir.iterdir()) == []
    assert [f["name"] for f in call(studio, "GET", "/api/state")["frames"]] == ["frame-001"]


def test_shoot_mode_routes_shutter_button(studio, tmp_path):
    def shot(name):
        f = tmp_path / name
        write_dng(f, make_negative())
        return f

    studio.camera_files([shot("a.DNG")])  # default: test first
    assert studio.test is not None and studio.roll.frames == {}
    with pytest.raises(urllib.error.HTTPError):
        call(studio, "POST", "/api/test/mode", {"mode": "nope"})
    assert call(studio, "POST", "/api/test/mode", {"mode": "direct"})["shoot_mode"] == "direct"
    studio.camera_files([shot("b.DNG")])
    assert list(studio.roll.frames) == ["frame-001"]


def test_test_shot_without_raw_says_why(studio, tmp_path):
    jpg = tmp_path / "x.JPG"
    jpg.write_bytes(b"\xff\xd8not really")
    studio.new_test([jpg])
    test = wait_for(lambda: studio.test["status"] != "analyzing" and studio.test_state())
    assert test["status"] == "error" and "Image Quality to RAW" in test["error"]
    with pytest.raises(ValueError):
        studio.keep_test()
    assert studio.test is not None  # still there to look at or discard


def test_leftover_test_shot_comes_back(tmp_path):
    source = raw_folder(tmp_path / "source", n=1)
    old = tmp_path / ".nlb" / "test"
    for n in ("0003", "0007"):
        (old / n).mkdir(parents=True)
        write_dng(old / n / "x.DNG", make_negative())
    st = Studio(tmp_path, roll="roll", fake_camera=source)
    assert st.test is not None and st.test["id"] == 8
    assert [p.name for p in old.iterdir()] == ["0008"]


# --- camera worker: missing gphoto2, no camera, hotplug ---

def wait_status(worker, status, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if worker.snapshot()["status"] == status:
            return worker.snapshot()
        time.sleep(0.02)
    raise AssertionError(f"status {worker.snapshot()['status']!r}, wanted {status!r}")


def test_camera_unavailable(tmp_path):
    worker = CameraWorker(lambda: pytest.fail("must not open a camera"), tmp_path / "in",
                          lambda files: None, unavailable="no gphoto2 here")
    worker.start()
    assert worker.snapshot()["status"] == "unavailable"
    with pytest.raises(RuntimeError, match="no gphoto2 here"):
        worker.submit("connect").result(timeout=5)
    with pytest.raises(RuntimeError):
        worker.submit("capture").result(timeout=5)
    snap = worker.snapshot()
    assert snap["status"] == "unavailable" and snap["message"] == "no gphoto2 here"


def test_camera_backend_import_error_does_not_hang(tmp_path):
    def make_backend():
        raise ImportError("No module named 'gphoto2'")
    worker = CameraWorker(make_backend, tmp_path / "in", lambda files: None)
    worker.start()
    with pytest.raises(RuntimeError):
        worker.submit("connect").result(timeout=5)
    assert worker.snapshot()["status"] == "error"  # not stuck on "connecting"


def test_camera_hotplug(tmp_path, monkeypatch):
    monkeypatch.setattr(camera_mod, "DETECT_EVERY", 0.05)
    source = raw_folder(tmp_path / "source", n=1)
    plugged = threading.Event()
    got = []

    def make_backend():
        if not plugged.is_set():
            raise RuntimeError("[-105] Unknown model")
        return FakeBackend(source)

    worker = CameraWorker(make_backend, tmp_path / "in", got.append, detect=plugged.is_set)
    worker.start()
    with pytest.raises(RuntimeError, match="No camera found"):
        worker.submit("connect").result(timeout=5)
    assert worker.snapshot()["status"] == "nocamera"

    plugged.set()  # connects by itself
    assert wait_status(worker, "ready")["model"].startswith("Fake camera")
    assert worker.submit("capture").result(timeout=5)

    worker.backend.preview = lambda: (_ for _ in ()).throw(OSError("unplugged"))
    plugged.clear()
    worker.add_viewer(1)  # live view notices the camera is gone
    wait_status(worker, "nocamera")
    worker.add_viewer(-1)
    plugged.set()
    wait_status(worker, "ready")

    # after an explicit disconnect, a replug doesn't grab the camera
    worker.submit("disconnect").result(timeout=5)
    plugged.clear()
    wait_status(worker, "nocamera")
    plugged.set()
    wait_status(worker, "disconnected")
    worker.submit("connect").result(timeout=5)
    assert worker.snapshot()["status"] == "ready"


@pytest.mark.skipif(darktable.executable() is None, reason="needs darktable-cli")
def test_darktable_engine(studio, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert call(studio, "GET", "/api/state")["darktable"]["available"]
    call(studio, "POST", "/api/camera/connect")
    call(studio, "POST", "/api/camera/capture", {})
    call(studio, "PATCH", "/api/frames/frame-001", {"engine": "darktable", "rotation": 90})
    # a new capture keeps the processing of the frame before it
    call(studio, "POST", "/api/camera/capture", {})
    assert call(studio, "GET", "/api/state")["frames"][1]["engine"] == "darktable"
    call(studio, "PATCH", "/api/frames/frame-002", {"engine": "nlb", "rejected": True})
    studio.pool.shutdown(wait=True)

    for view in ("crop", "full"):
        assert call(studio, "GET", f"/api/frames/frame-001/image?view={view}&size=thumb")[:2] == b"\xff\xd8"
    previews = tmp_path / "cache" / "nlb" / "darktable" / "previews"
    assert len(list(previews.glob("*.png"))) == 1

    # a picked film base becomes negadoctor's Dmin: a new darktable render
    call(studio, "POST", "/api/base", {"name": "frame-001", "x": 0.5, "y": 0.5})
    assert call(studio, "GET", "/api/frames/frame-001/image?size=thumb")[:2] == b"\xff\xd8"
    assert len(list(previews.glob("*.png"))) == 2
    assert (tmp_path / "cache" / "nlb" / "darktable" / "transforms.json").is_file()

    call(studio, "POST", "/api/render", {})
    while call(studio, "GET", "/api/state")["job"]["running"]:
        pass
    assert call(studio, "GET", "/api/state")["job"]["errors"] == []
    import cv2
    img = cv2.imread(str(studio.library / "roll-positive" / "frame-001.tif"), cv2.IMREAD_UNCHANGED)
    assert img.dtype == np.uint16 and img.shape[0] > img.shape[1]
