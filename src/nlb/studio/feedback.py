"""Test-shot feedback: capture measurements + camera settings -> what to change before shooting the roll.

`assess()` turns `develop.capture_metrics()` into checks, each with a status and, when
something should change, advice phrased as a physical or camera-setting action. Positions
are as seen in live view (sensor space). Targets follow sony-capture/README.md
("Exposing for inversion").
"""
import math

TARGET = 0.75                  # film base, brightest channel, as a fraction of full scale
OK_RANGE = (0.6, 0.85)
BAD_UNDER = 0.3                # below this the dense end is noisy: more than ~1.3 stops under
CLIP = 0.9
BASE_ISO = 100                 # A7 IV base ISO: most dynamic range
SHARP_APERTURE = (5.6, 11.0)
OFF_CENTER = 0.06              # picture center vs frame center, fraction of the frame
MIN_COVERAGE = 0.5             # picture long side vs frame long side
EVEN_LIGHT = 0.92              # dimmest rebate slice vs brightest
FLARE_MARGIN = 3.0             # densest film vs stray light, per channel
TILT_WARN = 1.0                # degrees
SOFT_EDGE = 9.0                # sprocket-hole edge width, sensor pixels: clearly out of focus
SOFTER = 1.2                   # vs the sharpest comparable test shot
SAME_EXPOSURE = 0.3            # stops: test shots this close are compared for sharpness
MATCH = 0.2                    # stops: base drift from the roll's reference

RANK = {"bad": 0, "warn": 1, "info": 2, "ok": 3}
CHANNELS = ("red", "green", "blue")


def check(key: str, label: str, status: str, value: str, advice: str = "") -> dict:
    return {"key": key, "label": label, "status": status, "value": value, "advice": advice}


# --- camera settings ---

def shutter_seconds(v) -> float | None:
    """Sony / gphoto2 shutter strings: "1/250", "0.5", "2", '2"', '1"3' (1.3 s)."""
    s = str(v).strip().lower().removesuffix("s")
    if '"' in s:
        s = s.replace('"', ".").rstrip(".")
    try:
        if "/" in s:
            a, b = s.split("/", 1)
            return float(a) / float(b)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


def iso_value(v) -> int | str | None:
    s = str(v).strip().lower()
    if "auto" in s:
        return "auto"
    try:
        return int(float(s))
    except ValueError:
        return None


def f_number(v) -> float | None:
    s = str(v).strip().lower().removeprefix("f/").removeprefix("f")
    try:
        return float(s)
    except ValueError:
        return None


def _value(config: dict, name: str):
    w = config.get(name)
    return w.get("value") if isinstance(w, dict) else None


def shutter_text(v) -> str:
    t = shutter_seconds(v)
    return f"{v} s" if t is not None and t >= 0.3 and "/" not in str(v) else str(v)


def describe_settings(config: dict) -> str:
    parts = []
    if (iso := _value(config, "iso")) is not None:
        parts.append(f"ISO {iso}")
    if (ss := _value(config, "shutterspeed")) is not None:
        parts.append(shutter_text(ss))
    if (fn := f_number(_value(config, "f-number"))) is not None:
        parts.append(f"f/{fn:g}")
    return " · ".join(parts)


def _nearest(options: list, target: float):
    return min(options, key=lambda o: abs(math.log2(o[1] / target)))


def suggest_exposure(stops: float, config: dict) -> str:
    """Camera settings that add `stops` of exposure (negative: take away), from its own choices.

    Also moves ISO to BASE_ISO and the aperture into SHARP_APERTURE when the camera reports
    them, and makes up for both with the shutter speed.
    """
    need, changes, was = stops, [], []
    iso = iso_value(_value(config, "iso"))
    if isinstance(iso, int) and iso != BASE_ISO:
        need += math.log2(iso / BASE_ISO)
        changes.append(f"ISO {BASE_ISO}")
        was.append(f"ISO {iso}")
    fn = f_number(_value(config, "f-number"))
    f_opts = [(c, v) for c in (config.get("f-number") or {}).get("choices", []) if (v := f_number(c))]
    if fn and f_opts and not SHARP_APERTURE[0] <= fn <= SHARP_APERTURE[1]:
        choice, new = _nearest(f_opts, 8.0)
        need += 2 * math.log2(new / fn)
        changes.append(f"f/{new:g}")
        was.append(f"f/{fn:g}")
    current = _value(config, "shutterspeed")
    now = shutter_seconds(current) if current is not None else None
    options = [(c, t) for c in (config.get("shutterspeed") or {}).get("choices", [])
               if (t := shutter_seconds(c))]
    if not now or not options:
        if abs(stops) < 0.15:
            return f"Set {' and '.join(changes)}." if changes else ""
        direction = "Lengthen" if need > 0 else "Shorten"
        extra = f" with {' and '.join(changes)}" if changes else ""
        return f"{direction} the exposure by {abs(need):.1f} stops{extra}."
    target = now * 2.0 ** need
    best, t = _nearest(options, target)
    if abs(math.log2(t / now)) >= 0.15:
        changes.append(f"the shutter to {shutter_text(best)}")
        was.append(shutter_text(current))
    if not changes:
        return ""
    text = f"Set {', '.join(changes[:-1]) + ' and ' if len(changes) > 1 else ''}{changes[-1]} (now {', '.join(was)})."
    short = math.log2(target / t)
    if short > 0.5:
        text += (f" That is the longest shutter the camera offers and still {short:.1f} stops short:"
                 " brighten the light or open the aperture.")
    elif short < -0.5:
        text += (f" That is the shortest shutter the camera offers and still {-short:.1f} stops over:"
                 " dim the light or stop the lens down.")
    return text


def settings_check(config: dict, exposure_advised: bool) -> dict | None:
    """ISO and aperture. When the exposure check already gives settings, those include these fixes."""
    if not config:
        return None
    status, advice = "ok", []
    iso = iso_value(_value(config, "iso"))
    if iso == "auto":
        status = "warn"
        advice.append(f"ISO is on Auto: set a fixed ISO {BASE_ISO} so every frame gets the same exposure.")
    elif isinstance(iso, int) and iso != BASE_ISO:
        status = "warn"
        advice.append(f"ISO {iso} has {'less highlight range (extended ISO)' if iso < BASE_ISO else 'less dynamic range'}"
                      f" than ISO {BASE_ISO}.")
    fn = f_number(_value(config, "f-number"))
    if fn is not None and not SHARP_APERTURE[0] <= fn <= SHARP_APERTURE[1]:
        status = "info" if status == "ok" else status
        advice.append(f"Around f/8 is sharpest at macro distances and covers film curl"
                      f"{'' if fn < SHARP_APERTURE[0] else '; smaller apertures soften from diffraction'}.")
    if advice:
        fix = "" if exposure_advised else suggest_exposure(0.0, config)
        advice.append(fix or "The exposure advice above includes this.")
    return check("settings", "Camera settings", status, describe_settings(config) or "—", " ".join(advice))


# --- the shot ---

def is_negative(m: dict) -> bool:
    """A film strip in a holder shows sprocket holes, holder, or both."""
    return m.get("angle") is not None or m.get("holder", 0) > 0.01 or m.get("edge_px") is not None


def exposure_check(m: dict, config: dict) -> dict:
    h = m["base_headroom"]
    stops = math.log2(TARGET / max(h, 1e-4))
    value = f"film base at {h:.0%} of full scale (target {OK_RANGE[0]:.0%}–{OK_RANGE[1]:.0%})"
    if m["film_clipped"] > 0.001 or h > CLIP:
        return check("exposure", "Exposure", "bad", value,
                     f"The film is clipping. {suggest_exposure(min(stops, -0.5), config)}")
    if h < OK_RANGE[0]:
        status = "bad" if h < BAD_UNDER else "warn"
        why = ("dense areas (bright skies, highlights) will be noisy" if status == "bad"
               else "a little more exposure lowers noise in the dense areas")
        return check("exposure", "Exposure", status, value,
                     f"{stops:.1f} stops under: {why}. {suggest_exposure(stops, config)} "
                     "Sprocket holes may clip; that's fine.")
    if h > OK_RANGE[1]:
        return check("exposure", "Exposure", "warn", value,
                     f"Close to clipping. {suggest_exposure(stops, config)}")
    return check("exposure", "Exposure", "ok", value)


def framing_check(m: dict) -> dict:
    box = m.get("picture")
    if box is None:
        return check("framing", "Framing", "bad", "picture area not found",
                     "Center a frame (not the gap between frames) in the holder, with the light on.")
    x, y, w, h = box
    W, H = m.get("size") or (3, 2)
    status, advice = "ok", []
    cut = [side for side, hit in (("left", x < 0.005), ("right", x + w > 0.995),
                                  ("top", y < 0.005), ("bottom", y + h > 0.995)) if hit]
    if cut:
        status = "bad"
        advice.append(f"The picture runs off the {' and '.join(cut)} edge: back the camera off a "
                      "little or recenter the holder.")
    coverage = max(w * W, h * H) / max(W, H)
    if coverage < MIN_COVERAGE:
        status = "warn" if status == "ok" else status
        advice.append(f"The picture spans only {coverage:.0%} of the frame: move the camera closer "
                      "for more pixels on the film, keeping holes and a sliver of holder in view.")
    dx, dy = x + w / 2 - 0.5, y + h / 2 - 0.5
    off = [f"{'right' if dx > 0 else 'left'} by {abs(dx):.0%}" if abs(dx) > OFF_CENTER else "",
           f"{'low' if dy > 0 else 'high'} by {abs(dy):.0%}" if abs(dy) > OFF_CENTER else ""]
    off = [o for o in off if o]
    if off and not cut:
        status = "warn" if status == "ok" else status
        advice.append(f"The picture sits off center ({', '.join(off)} of the frame): recenter it.")
    value = f"picture spans {coverage:.0%} of the frame" + ("" if off or cut else ", centered")
    return check("framing", "Framing", status, value, " ".join(advice))


def references_check(m: dict) -> dict:
    holes, holder = m.get("angle") is not None or m.get("edge_px") is not None, m.get("holder", 0) > 0.01
    if holes and holder:
        return check("refs", "Holes & holder", "ok", "sprocket holes and holder edge in view")
    if not holes:
        return check("refs", "Holes & holder", "warn", "no sprocket holes found",
                     "Keep a row of sprocket holes in view: the engine reads the light from them "
                     "and levels the strip by them.")
    return check("refs", "Holes & holder", "info", "no holder edge in view",
                 "Show a sliver of the holder beside the film so stray light (flare) can be "
                 "measured and removed.")


def tilt_check(m: dict) -> dict | None:
    a = m.get("angle")
    if a is None:
        return None
    if abs(a) < 0.3:
        return check("tilt", "Level", "ok", f"strip level ({a:+.1f}°)")
    turn = "counter-clockwise" if a > 0 else "clockwise"
    if abs(a) < TILT_WARN:
        return check("tilt", "Level", "ok", f"strip tilted {abs(a):.1f}°; deskew fixes it")
    return check("tilt", "Level", "warn", f"strip tilted {abs(a):.1f}°",
                 f"Turn the holder about {abs(a):.1f}° {turn} (as seen in live view). "
                 "Deskewing costs picture at the corners.")


def light_check(m: dict) -> dict | None:
    fo = m.get("falloff")
    if not fo:
        return None
    along = ("left", "middle", "right") if fo["axis"] == "x" else ("top", "middle", "bottom")
    across = ("top", "bottom") if fo["axis"] == "x" else ("left", "right")
    slices = list(zip(along, fo["along"])) + list(zip(across, fo["across"]))
    side, low = min(slices, key=lambda s: s[1])
    if low >= EVEN_LIGHT:
        return check("light", "Even light", "ok", f"within {1 - low:.0%} across the film")
    where = "in the middle" if side == "middle" else f"toward the {side}"
    return check("light", "Even light", "warn", f"{1 - low:.0%} dimmer {where}",
                 "Center the film over the light, add diffusion, or move the light so its edge "
                 "isn't under the film. (A flat-field frame of the bare light corrects what's left.)")


def flare_check(m: dict) -> dict | None:
    ratio = m.get("floor_over_flare")
    if not ratio:
        return None
    i = min(range(len(ratio)), key=lambda k: ratio[k])
    value = f"densest film {ratio[i]:.1f}× above stray light ({CHANNELS[i]})"
    if ratio[i] >= FLARE_MARGIN:
        return check("flare", "Stray light", "ok", value)
    return check("flare", "Stray light", "warn", value,
                 "Light that misses the film is veiling the dense areas: mask the lightbox around "
                 "the holder, turn off room lights, and use a lens hood.")


def focus_check(m: dict, best: dict | None, scale: float) -> dict | None:
    if m.get("edge_px") is None:
        return None
    edge = m["edge_px"] * scale
    value = f"hole edges {edge:.1f} px wide"
    if edge > SOFT_EDGE:
        return check("focus", "Focus", "warn", value,
                     "Edges look soft: refocus at 4× in live view, and check the film lies flat.")
    if best is None:
        return check("focus", "Focus", "ok", value,
                     "First test shot at this exposure: refocus and shoot again to compare.")
    ref = best["edge_px"] * scale
    if edge > SOFTER * ref:
        return check("focus", "Focus", "warn", f"{value}, test shot {best['id']} was {ref:.1f} px",
                     f"Softer than test shot {best['id']}: refocus at 4× in live view.")
    sharpest = edge <= ref
    return check("focus", "Focus", "ok", value + (", sharpest so far" if sharpest else
                                                  f", close to test shot {best['id']} ({ref:.1f} px)"))


def match_check(m: dict, reference: dict | None) -> dict | None:
    if not reference:
        return None
    ref = reference["base"]
    ch = max(range(3), key=lambda k: ref[k])
    stops = math.log2(max(m["base"][ch], 1e-6) / max(ref[ch], 1e-6))
    label = reference["label"]
    if abs(stops) <= MATCH:
        return check("match", "Matches roll", "ok", f"within {abs(stops):.1f} stops of {label}")
    return check("match", "Matches roll", "warn",
                 f"{abs(stops):.1f} stops {'brighter' if stops > 0 else 'darker'} than {label}",
                 "The exposure or light changed since then, so this frame won't match the roll. "
                 "Go back to the earlier settings, or if the change is on purpose, re-pick the "
                 "film base (and re-lock levels) after keeping.")


def assess(m: dict, config: dict, reference: dict | None = None, best: dict | None = None,
           scale: float = 1.0) -> dict:
    """-> {"verdict": "good" | "adjust" | "bad", "summary", "checks": [worst first]}.

    `reference`: {"label", "base"} to compare exposure against (the roll's picked base or
    its last frame). `best`: the sharpest earlier test shot at about the same exposure,
    {"id", "edge_px"}. `scale`: sensor pixels per `edge_px` pixel.
    """
    if max(m.get("light") or [0]) < 0.02:
        checks = [check("dark", "Exposure", "bad", "frame is nearly black",
                        "Is the light on and the lens cap off? "
                        + suggest_exposure(math.log2(TARGET / 0.02), config))]
    elif not is_negative(m):
        checks = [check("film", "Negative", "bad", "no sprocket holes or holder found",
                        "This doesn't look like film in the holder. Put a strip in the holder "
                        "on the light, holes and holder edge in view.")]
    else:
        checks = [exposure_check(m, config), framing_check(m), references_check(m),
                  tilt_check(m), light_check(m), flare_check(m), focus_check(m, best, scale),
                  match_check(m, None if m["film_clipped"] > 0.001 else reference)]
    advised = any(c and c["key"] == "exposure" and c["advice"] for c in checks)
    checks.append(settings_check(config, advised))
    checks = sorted((c for c in checks if c), key=lambda c: RANK[c["status"]])
    worst = checks[0]["status"] if checks else "ok"
    fixes = sum(c["status"] in ("bad", "warn") for c in checks)
    if worst == "bad":
        verdict, summary = "bad", "Fix this before keeping: " + checks[0]["label"].lower() + "."
    elif fixes:
        verdict, summary = "adjust", f"Usable, but {fixes} thing{'s' if fixes > 1 else ''} to improve."
    else:
        verdict, summary = "good", "Looks good. Keep it, or shoot again to compare."
    return {"verdict": verdict, "summary": summary, "checks": checks}
