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

    # ---- guesses ----
    lens_len: float = 125     # Laowa barrel length, mount to front
    lens_r: float = 37        # Laowa barrel radius

    # ---- picks (chosen, not measured) ----
    gw: float = 92            # gate width
    gate_d: float = 30        # gate depth
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
    film_slot_w: float = 5        # side walls' film slot, along x
    film_slot_clear: float = 1    # ... and the film's width plus this much each side, along y
    rear_win_w: float = 46        # rear wall window, toward the light
    rear_win_h: float = 34
    tab_t: float = 2              # lock switch tab thickness, x
    tab_clear: float = 0.5        # clearance each side of the tab in the lid slot
    slot_end: float = 3           # the lid slot runs this far past the tab's travel at each end
    pad: float = 4                # pressure plate pad footprint, square
    pad_z: float = 22             # pad centres at z = +-pad_z
    pad_dy: float = 15.5          # ... and at y = axis +- pad_dy
    lid_text_size: float = 5.5    # font size, em height; the letters then fill the 16 x 4.4 boxes
    lid_text_depth: float = 0.4   # engraving depth
    lid_text_z: float = 14        # SLIDE centred at z = -lid_text_z, LOCK at +lid_text_z
    lid_text_back: float = 11     # lettering centred this far in front (-x) of the knob
    lid_text_w: float = 16        # each word's box: along z, ...
    lid_text_h: float = 4.4       # ... and along x
    wedge_t: float = 2            # lock switch wedge plate thickness, x
    wedge_w: float = 70           # ... and width, z
    wedge_win_w: float = 52       # its window along z (the height is win_h): shifted +-sw_travel/2 it still clears win_w
    wedge_clear: float = 0.5      # its clearance to the gate's floor and to the lid's underside
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
    shroud_w: float = 60          # ... shroud outside width, z, ...
    shroud_h: float = 46          # ... opening height, y, centred on the axis, ...
    shroud_t: float = 2           # ... and wall thickness (side walls and top plate)

    # ---- reference solids in the assembly (not printed) ----
    film_strip_len: float = 228   # the film strip drawn through the gate, along z, ...
    film_strip_z: float = 19      # ... centred here (mockup line 470)

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
    def dock_x0(self) -> float:
        return self.x_gate + self.gate_d

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
    def film_slot_h(self) -> float:     # side walls' film slot, along y: 37
        return self.film_w + 2 * self.film_slot_clear

    @property
    def film_slot_x0(self) -> float:    # ... and its lens-side edge: flush with the front plate's front face, so the
        return self.x_front_plate       # slot opens only behind the front plate, none of it into the lens-side chamber

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
