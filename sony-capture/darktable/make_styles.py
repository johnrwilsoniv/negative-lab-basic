"""Generate darktable styles for inverting negatives shot on the A7 IV lightbox rig.

    python3 make_styles.py          # writes *.dtstyle next to this file

Params are packed to match darktable 5.6's module structs (negadoctor v2,
temperature v4, exposure v7, channelmixerrgb v3). Calibration values come
from test/frame-001.ARW (ISO 125, 1/5 s); see README.md for the method.
"""

import struct
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent

# darktable's default blend params (blending off), blendop v14, as stored in XMP
DEFAULT_BLEND = "gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU="
BLENDOP_VERSION = 14

# Raw-space colour of the backlight, measured through the sprocket holes (R/G, B/G).
# White balance divides it out so the light source is neutral.
LIGHT_RG, LIGHT_BG = 0.383, 0.533
# Brings the backlight to 1.0 at 1/5 s, ISO 125 (it sat ~0.72 EV below clipping).
EXPOSURE_EV = 0.72
# Veiling flare, as a fraction of the (pre-exposure) light. Measured on the opaque
# surround next to the film; without removing it the blue channel's density range
# is crushed and shadows go blue.
FLARE_BLACK = 0.003


def f32(*v):
    return struct.pack(f"<{len(v)}f", *v)


def temperature(r, g, b):
    preset_user = 2
    return f32(r, g, b, 0.0) + struct.pack("<i", preset_user)


def exposure(ev, black):
    mode_manual, deflicker_pct, deflicker_target = 0, 50.0, -4.0
    compensate_bias, compensate_hilite = 0, 0
    return struct.pack("<iffffii", mode_manual, black, ev, deflicker_pct, deflicker_target,
                       compensate_bias, compensate_hilite)


def negadoctor(film_stock, Dmin, wb_high, wb_low, D_max, offset, black, gamma, soft_clip, exposure):
    b = struct.pack("<i", film_stock) + f32(*Dmin, 0.0) + f32(*wb_high, 0.0) + f32(*wb_low, 0.0)
    b += f32(D_max, offset, black, gamma, soft_clip, exposure)
    assert len(b) == 76
    return b


# darktable's built-in "monochrome | luminance-based" color calibration preset:
# grey output from the green channel, no chromatic adaptation.
MONOCHROME = bytes.fromhex(
    "0000803f000000000000000000000000000000000000803f00000000000000000000000000000000"
    "0000803f000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000803f0000000000000000000000000000000000000000000000000000000001000000"
    "00000000020000000400000003000000a9fbb03e508db73e00589c45000000000100000002000000")
assert len(MONOCHROME) == 160

# Empty params: darktable fills in the module's defaults (only used for disabled entries).
DISABLED = b""


def plugin(num, op, version, params, enabled=True, instance=""):
    # A named instance is a second one (multi_priority 1) next to the image's default
    priority, hand_edited = (1, 1) if instance else (0, 0)
    return f"""  <plugin>
   <num>{num}</num>
   <module>{version}</module>
   <operation>{op}</operation>
   <op_params>{params.hex()}</op_params>
   <enabled>{int(enabled)}</enabled>
   <blendop_params>{DEFAULT_BLEND}</blendop_params>
   <blendop_version>{BLENDOP_VERSION}</blendop_version>
   <multi_priority>{priority}</multi_priority>
   <multi_name>{escape(instance)}</multi_name>
   <multi_name_hand_edited>{hand_edited}</multi_name_hand_edited>
  </plugin>"""


def style(name, description, items):
    plugins = "\n".join(plugin(i, *item) for i, item in enumerate(items))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<darktable_style version="1.0">
 <info>
  <name>{escape(name)}</name>
  <description>{escape(description)}</description>
 </info>
 <style>
{plugins}
 </style>
</darktable_style>
"""


# Applying a style in darktable's default "append" mode adds an *enabled* entry for a
# multi-instance module (exposure, color calibration) as a new instance; only disabled
# entries replace the image's existing one. So each of those gets a disabled entry that
# switches off the auto-applied instance, then a named instance with our settings.
def rig_items():
    """Modules shared by both styles: neutral backlight, fixed exposure, flare removed."""
    return [
        ("temperature", 4, temperature(1 / LIGHT_RG, 1.0, 1 / LIGHT_BG)),
        ("exposure", 7, DISABLED, False),
        ("exposure", 7, exposure(EXPOSURE_EV, FLARE_BLACK), True, "negative scan"),
        # negadoctor prints to display-referred 0..1; a scene-referred tone mapper on top flattens it
        ("agx", 7, DISABLED, False),
        ("sigmoid", 3, DISABLED, False),
        ("filmicrgb", 6, DISABLED, False),
    ]


C41 = negadoctor(
    film_stock=1,
    Dmin=(0.367, 0.177, 0.0855),        # film base, relative to the backlight
    wb_high=(1.271, 1.0, 0.755),
    wb_low=(0.799, 1.0, 1.358),
    D_max=1.121,
    offset=-0.352,
    black=-0.353,
    gamma=4.0,
    soft_clip=0.75,
    exposure=1.609,
)

BW = negadoctor(
    film_stock=0,
    Dmin=(0.75, 0.75, 0.75),            # placeholder: pick it on the clear rebate
    wb_high=(1.0, 1.0, 1.0),
    wb_low=(1.0, 1.0, 1.0),
    D_max=2.2,                          # darktable's B&W preset
    offset=-0.05,
    black=0.0755,
    gamma=5.0,
    soft_clip=0.75,
    exposure=1.0,
)

STYLES = {
    "negative-c41.dtstyle": style(
        "negative | C-41 (A7 IV lightbox)",
        "Colour negative on the A7 IV + lightbox rig: neutral backlight WB, +0.72 EV, flare "
        "black, negadoctor fitted on test/frame-001. Re-pick Dmin on the rebate per roll.",
        rig_items() + [
            # a per-image CAT would re-balance each frame from the camera's auto WB
            ("channelmixerrgb", 3, DISABLED, False),
            ("negadoctor", 2, C41),
        ]),
    "negative-bw.dtstyle": style(
        "negative | B&W (A7 IV lightbox)",
        "B&W negative on the A7 IV + lightbox rig: neutral backlight WB, +0.72 EV, flare black, "
        "monochrome from green, negadoctor B&W. Pick Dmin, D max and offset per roll.",
        rig_items() + [
            ("channelmixerrgb", 3, DISABLED, False),
            ("channelmixerrgb", 3, MONOCHROME, True, "monochrome"),
            ("negadoctor", 2, BW),
        ]),
}


if __name__ == "__main__":
    for filename, xml in STYLES.items():
        (HERE / filename).write_text(xml)
        print(HERE / filename)
