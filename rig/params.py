"""Every dimension of the scan rig, in mm, in mockup coordinates.

x is the optical axis, camera (-) to light (+), x = 0 at the lens mount. y is up from the
table. z is across the gate, the direction the film travels. Names are the mockup's
constants in snake_case; derived values mirror its `rebuild()` (names in brackets).

Callers vary the inputs by constructing: `Params(wd=150)`.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    """The rig's dimensions.

    User inputs `wd` and `axis`: the mockup still tags them "guess", and PLAN.md says to ask
    the user whether they were measured. Constructing one with `axis` below `axis_min` raises
    ValueError: the lens adapter would go through the table.
    """

    # ---- user inputs ----
    wd: float = 130           # lens front to film plane
    axis: float = 42.5        # table to lens centre

    # ---- known (datasheets) ----
    thread_major: float = 67        # Laowa filter thread M67 x 0.75: major diameter
    thread_pitch: float = 0.75
    csl_l: float = 165              # CS-Lite body 165 x 112 x 20
    csl_h: float = 112
    csl_t: float = 20
    csl_lit_w: float = 149          # CS-Lite lit area 149 x 95
    csl_lit_h: float = 95
    film_w: float = 35              # 35mm film
    film_t: float = 0.13
    frame_w: float = 36             # frame 36 x 24
    frame_h: float = 24
    perf_pitch: float = 4.75        # ISO 1007 (135) KS perforations: pitch along the film, ...
    perf_l: float = 1.98            # ... each this long along the film, ...
    perf_w: float = 2.79            # ... this wide across it, ...
    perf_r: float = 0.5             # ... with this corner radius, ...
    perf_edge: float = 2.01         # ... this far in from the film's edge
    perfs_per_frame: int = 8        # a frame advances 8 perforations: 38

    # ---- guesses ----
    lens_len: float = 125     # Laowa barrel length, mount to front
    lens_r: float = 37        # Laowa barrel radius

    # ---- picks (chosen, not measured) ----
    gw: float = 92            # gate width
    gate_front: float = 14    # gate front wall to film
    wall: float = 3
    win_w: float = 38         # gate window
    win_h: float = 26
    gap: float = 25           # film to light face
    tube_ro: float = 36
    tube_ri: float = 32
    flange: float = 3         # adapter flange thickness
    thread_len: float = 4.5
    thread_clear: float = 0.15    # radial clearance on the printed thread, 0.1-0.2 for FDM
    thread_lead_in: float = 45    # chamfer on the thread's free end, degrees from the axis
    adapter_r: float = 39         # adapter OD 78
    adapter_bore_r: float = 31    # adapter bore 62, clears the lens front element
    socket_depth: float = 9
    coupon_grip: float = 2        # thread test coupon: grip ring thickness (Ø78 / Ø62, as the flange)
    channel: float = 0.6      # film channel in slide mode
    sw_travel: float = 10     # lock switch travel
    ramp_len: float = 12
    ramp_min: float = 0.1
    ramp_rise: float = 0.7
    gate_above_axis: float = 36   # gate box height above the lens axis
    front_wall: float = 4         # gate front wall thickness
    fit_clear: float = 0.3        # radial clearance of the tube in its sockets
    plate_clear: float = 0.25     # pressure plate to the floor, the lid and each side wall: it drops in and floats
    lid_clear: float = 0.2        # gate lid to the front wall and to the rear wall, at each end
    csl_clear: float = 0.5        # CS-Lite slot between the dock's lips, beyond the panel's thickness (all behind it)
    baffle_h: float = 1.0         # tube baffle rib height; tube_ri - baffle_h is the adapter bore, so no vignetting
    baffle_pitch: float = 8       # rib to rib along the tube
    baffle_margin: float = 2      # no rib this close to either tube end
    plate_t: float = 1.8          # front plate and pressure plate thickness
    wedge_gap: float = 0.9        # pressure plate back face to wedge plate
    film_slot_w: float = 3.2      # side walls' film slot, along x
    film_slot_clear: float = 0.2  # ... and along y: its floor is flush under the film's lower edge, which rests on it, and
                                  # its roof this far above the upper edge, so the strip slides (F13)
    rear_win_w: float = 46        # rear wall window, toward the light
    rear_win_h: float = 34
    tab_t: float = 2              # lock switch tab thickness, x
    tab_clear: float = 0.5        # clearance each side of the tab in the lid slot
    slot_end: float = 3           # the lid slot runs this far past the tab's travel at each end
    pad: float = 4                # pressure plate pad footprint, square
    pad_z: float = 22             # pad centres at z = +-pad_z
    pad_dy: float = 15.5          # ... and at y = axis +- pad_dy
    lid_text_size: float = 5.5    # SLIDE / LOCK lettering, engraved in the gate front's top beside the lid (F5): font size,
                                  # em height; the letters then fill the 16 x 4.4 boxes
    lid_text_depth: float = 0.4   # engraving depth
    lid_text_z: float = 14        # SLIDE centred at z = -lid_text_z, LOCK at +lid_text_z
    lid_text_back: float = 11     # lettering centred this far in front (-x) of the knob
    lid_text_w: float = 16        # each word's box: along z, ...
    lid_text_h: float = 4.4       # ... and along x
    wedge_t: float = 2            # lock switch wedge plate thickness, x
    wedge_w: float = 70           # ... and width, z
    wedge_win_w: float = 52       # its window along z (the height is win_h): shifted +-sw_travel/2 it still clears win_w
    wedge_clear: float = 0.5      # its clearance to the gate's floor and to the lid's underside
    wedge_back_clear: float = 0.05  # ... and to the backer behind it, a block on the gate body's floor (F12): the clamp
                                    # pushes the plate back onto it, so this much of the preload is lost
    tab_w: float = 4              # lock switch tab width, z (thickness is tab_t)
    knob_w: float = 10            # lock switch knob: along x, ...
    knob_h: float = 5             # ... up from the lid top (grip ridges not counted), ...
    knob_l: float = 12            # ... and along z
    ridges: int = 3               # grip ridges on the knob, running the knob's length, centred on x_knob
    ridge_w: float = 1.2          # ... each this wide, along x
    ridge_h: float = 0.8          # ... this tall
    ridge_pitch: float = 3        # ... and this far apart, centre to centre
    dock_extra_w: float = 16      # light dock: floor width beyond the CS-Lite's length, 8 each side
    dock_tail: float = 6          # ... floor length past the slot's back edge (the back lip's front face)
    floor_t: float = 4            # ... floor thickness
    lip_h: float = 12             # ... front and back lips, above the floor, ...
    lip_t: float = 4              # ... and this thick along x; the slot between them is csl_slot
    cheek_top: float = 62         # ... side cheeks, up to this y (above the table)
    cheek_clear: float = 0.5      # ... their inner faces this far from the CS-Lite's ends
    dock_gate_clear: float = 0.2  # ... the gate sits in a notch in its floor and front lip (F10), this much clear each side
                                  # and to the front wall (F11)
    dock_front_t: float = 4       # ... front wall, in front of the gate front, holding the gate together (F11), ...
    dock_tube_clear: float = 1    # ... with a U around the tube, this much clear of it radially
    ear_w: float = 9              # gate joint (F5): screw pillars outside the side walls, this wide in z, ...
    ear_h: float = 9              # ... and this tall in y, at the bottom and under the lid; 1.25 around the counterbore
    joint_hole_d: float = 3.4     # ... M3 clearance through the gate front, ...
    cbore_d: float = 6.5          # ... counterbored for the head, ...
    cbore_depth: float = 3.5
    pilot_d: float = 2.5          # ... into a pilot the M3 self-taps (4.0 for an M3 heat-set insert), ...
    pilot_depth: float = 12       # ... this deep into the pillar

    # ---- reference solids in the assembly (not printed) ----
    film_strip_len: float = 228   # the film strip drawn through the gate, along z, ...
    film_strip_z: float = 19      # ... centred here (mockup line 470): six frames, the third centred in the window

    # ---- assumed, not confirmed with the user ----
    bed_x: float = 220
    bed_y: float = 220

    def __post_init__(self) -> None:
        if self.axis < self.axis_min:
            raise ValueError(
                f"axis {self.axis:g} is too low: the {2 * self.adapter_r:g} mm lens adapter would hit the table; "
                f"the lowest axis is {self.axis_min:g} (adapter_r)"
            )

    # ---- derived ----
    @property
    def axis_min(self) -> float:        # lowest lens axis: the adapter, the widest thing on it, just reaches the table
        return self.adapter_r

    @property
    def x_front(self) -> float:
        return self.lens_len

    @property
    def x_film(self) -> float:          # [xFilm]
        return self.lens_len + self.wd

    @property
    def x_gate(self) -> float:          # [xGate]
        return self.x_film - self.gate_front

    @property
    def x_light(self) -> float:         # [xLight]
        return self.x_film + self.gap

    @property
    def gh(self) -> float:              # [GH] gate box height
        return self.axis + self.gate_above_axis

    @property
    def gate_d(self) -> float:          # [GATE_D] gate depth: the body's rear face is the CS-Lite's lit face (F10)
        return self.gate_front + self.gap

    # Thread profile: ISO 68-1 external thread, crest and root left flat (truncated), the whole
    # profile moved inward by `thread_clear`.
    @property
    def thread_h(self) -> float:        # height of the fundamental 60 degree triangle, 0.866 P
        return self.thread_pitch * math.sqrt(3) / 2

    @property
    def thread_crest_r(self) -> float:  # major diameter 67, less the clearance
        return self.thread_major / 2 - self.thread_clear

    @property
    def thread_root_r(self) -> float:   # external minor diameter d3 = d - 17/12 H (66.08), less the clearance
        return self.thread_major / 2 - 17 / 24 * self.thread_h - self.thread_clear

    @property
    def thread_crest_flat(self) -> float:   # axial width of the flat crest, P/8
        return self.thread_pitch / 8

    @property
    def tube_x0(self) -> float:
        return self.x_front + self.flange

    @property
    def tube_x1(self) -> float:
        return self.x_gate + self.front_wall

    @property
    def tube_len(self) -> float:        # wd - 13
        return self.tube_x1 - self.tube_x0

    @property
    def tube_max_len(self) -> float:    # printed upright: no bed height is given, so assume as tall as the bed is wide
        return min(self.bed_x, self.bed_y)

    @property
    def baffle_count(self) -> int:      # ribs at exactly baffle_pitch, as many as fit between the end margins
        room = self.tube_len - 2 * self.baffle_margin
        if self.baffle_h <= 0 or room < self.baffle_h:
            return 0
        return int((room - self.baffle_h) / self.baffle_pitch + 1e-9) + 1

    @property
    def fit_r(self) -> float:           # adapter socket and gate hole radius
        return self.tube_ro + self.fit_clear

    @property
    def dock_w(self) -> float:
        return self.csl_l + self.dock_extra_w

    @property
    def dock_x0(self) -> float:         # the front wall's front face: the gate (front and body) is inset between it and the
        return self.x_gate - self.dock_gate_clear - self.dock_front_t   # CS-Lite (F11)

    @property
    def csl_slot(self) -> float:        # the CS-Lite's slot between the dock's lips, along x
        return self.csl_t + self.csl_clear

    @property
    def dock_x1(self) -> float:         # dock_tail past the slot's back edge
        return self.x_light + self.csl_slot + self.dock_tail

    @property
    def x_front_plate(self) -> float:   # front plate's front face; its rear face is channel/2 before the film
        return self.x_film - self.channel / 2 - self.plate_t

    @property
    def x_pp(self) -> float:            # [xPP] pressure plate back face
        return self.x_film + self.channel / 2 + self.plate_t

    @property
    def x_wedge(self) -> float:         # [xWedge] wedge plate front face
        return self.x_pp + self.wedge_gap

    @property
    def x_knob(self) -> float:          # [xKnob]
        return self.x_wedge + 1

    @property
    def film_slot_h(self) -> float:     # side walls' film slot, along y: 35.2
        return self.film_w + self.film_slot_clear

    @property
    def film_slot_y0(self) -> float:    # ... from the film's lower edge, so the film stays centred on the window
        return self.axis - self.film_w / 2

    @property
    def frame_pitch(self) -> float:     # frame to frame along the film: 38, so 2 of unexposed film between frames
        return self.perfs_per_frame * self.perf_pitch

    @property
    def perf_inner(self) -> float:      # the axis to the perforations' inner edges, along y: 12.7, 0.7 past the frame
        return self.film_w / 2 - self.perf_edge - self.perf_w

    @property
    def frame_zs(self) -> list[float]:  # centres of the frames on the reference strip: one at z = 0, in the window,
        k0 = math.ceil((self.film_strip_z - self.film_strip_len / 2 + self.frame_w / 2) / self.frame_pitch - 1e-9)
        k1 = math.floor((self.film_strip_z + self.film_strip_len / 2 - self.frame_w / 2) / self.frame_pitch + 1e-9)
        return [k * self.frame_pitch for k in range(k0, k1 + 1)]   # the rest every frame_pitch, all wholly on the strip

    @property
    def perf_zs(self) -> list[float]:   # centres of each row's perforations: half a pitch either side of each frame
        half = self.perf_pitch / 2      # centre, so a frame spans 8 of them, and all wholly on the strip
        j0 = math.ceil((self.film_strip_z - self.film_strip_len / 2 + self.perf_l / 2 - half) / self.perf_pitch - 1e-9)
        j1 = math.floor((self.film_strip_z + self.film_strip_len / 2 - self.perf_l / 2 - half) / self.perf_pitch + 1e-9)
        return [half + j * self.perf_pitch for j in range(j0, j1 + 1)]

    @property
    def x_ref(self) -> float:          # the film reference plane (F5): the gate front's rear face, which prints on the
        return self.x_film - self.channel / 2   # bed; the film lies against it, half the channel in front of the film plane

    @property
    def gate_front_w(self) -> float:    # the gate front, as wide as the body and its screw pillars
        return self.gw + 2 * self.ear_w

    @property
    def flare_scale(self) -> float:     # the light passage flares from the frame window to this times its size at the
        return 2 * self.tube_ri / math.hypot(self.win_w, self.win_h)    # tube end: its corners on the tube's bore

    @property
    def screw_points(self) -> list[tuple[float, float]]:    # (y, z) of the four gate joint screws, one per pillar
        ys = (self.ear_h / 2, self.gh - self.wall - self.ear_h / 2)
        zs = (-(self.gw / 2 + self.ear_w / 2), self.gw / 2 + self.ear_w / 2)
        return [(y, z) for y in ys for z in zs]

    @property
    def film_slot_x0(self) -> float:    # ... and its lens-side edge: flush with the front plate's rear face, so the
        return self.x_front_plate + self.plate_t    # side wall covers the plate's end (flush with its front face
                                        # the two met only along an edge, which Onshape rejects) and the slot opens only
                                        # behind the front plate, none of it into the lens-side chamber

    def ramp_t(self, u: float) -> float:        # [rampT] ramp thickness at u along the ramp
        return self.ramp_min + self.ramp_rise * (self.ramp_len / 2 - u) / self.ramp_len

    def clamp_shift(self, s: float) -> float:   # [clampShift] pressure plate travel, knob at s
        return min(self.ramp_t(-s) - self.ramp_t(self.sw_travel / 2), self.channel - self.film_t)

    @property
    def pad_t(self) -> float:           # [padT] pad thickness at the pad centre
        return self.x_wedge - self.ramp_t(self.sw_travel / 2) - self.x_pp

    @property
    def lock_shift(self) -> float:      # pressure plate travel at LOCK
        return self.clamp_shift(self.sw_travel / 2)

    @property
    def preload(self) -> float:         # pad/ramp overlap at LOCK
        return (
            self.ramp_t(-self.sw_travel / 2)
            - self.ramp_t(self.sw_travel / 2)
            - (self.channel - self.film_t)
        )


DEFAULT = Params()
