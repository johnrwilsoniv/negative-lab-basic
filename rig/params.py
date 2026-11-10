"""Every dimension of the scan rig, in mm, in mockup coordinates.

x is the optical axis, camera (-) to light (+), x = 0 at the lens mount. y is up from the
table. z is across the gate, the direction the film travels. Names are the mockup's
constants in snake_case where the mockup has them; the film transport (gate, sprocket drive,
spools: ruling D1) is newer than the mockup and has its own.

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
    film_roll_len: float = 1600     # an uncut 36 exposure roll, 36 x 38 plus leader and trailer

    # ---- guesses ----
    lens_len: float = 125     # Laowa barrel length, mount to front
    lens_r: float = 37        # Laowa barrel radius
    roll_pack: float = 1.15   # a hand-wound roll takes this much more room than the film's own cross-section

    # ---- picks (chosen, not measured) ----
    # lens adapter and tube
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
    fit_clear: float = 0.3        # radial clearance of the tube in its sockets
    baffle_h: float = 1.0         # tube baffle rib height; tube_ri - baffle_h is the adapter bore, so no vignetting
    baffle_pitch: float = 8       # rib to rib along the tube
    baffle_margin: float = 2      # no rib this close to either tube end

    # film gate: the gate front and the gate body (D2)
    gw: float = 92            # gate width, z: the front and the body
    gate_front: float = 14    # gate front's front face to the film
    gate_above_axis: float = 36   # gate height above the lens axis
    front_wall: float = 4         # the tube socket's depth in the gate front
    win_w: float = 38         # frame window, at the film, in the gate front
    win_h: float = 26
    win_depth: float = 1.8    # ... running straight this far forward from the reference plane, then flaring to the tube
    gap: float = 25           # film to light face
    channel: float = 0.3      # the film channel: recessed this deep into the gate body's front face, closed by the
                              # gate front's flat rear face. Fixed; nothing clamps (D2)
    channel_clear: float = 0.2    # ... and this much taller than the film, so the strip slides without wandering in y
    lead_in: float = 3            # the channel opens up over this length at each side of the body, ...
    lead_in_depth: float = 1.0    # ... to this deep, so the film's end finds its way in
    body_win_w: float = 40        # light passage through the gate body: this at its front face, ...
    body_win_h: float = 28
    rear_win_w: float = 46        # ... this at its rear face, on the lit face: the frame's chief rays and the lens's
    rear_win_h: float = 34        #     cone, 25 behind the film, fit inside it
    peg_d: float = 4              # friction pegs on the gate body's front face, into holes in the gate front (D2), ...
    peg_len: float = 6
    peg_fit: float = 0.0          # ... the holes this much bigger in diameter: 0, since FDM prints holes a little small,
                                  #     so it presses. Open it if the front won't go on
    peg_hole_extra: float = 0.5   # the holes this much deeper than the pegs, so a peg never bottoms out
    peg_chamfer: float = 0.5      # lead-in on each peg's tip
    peg_y_lo: float = 10          # peg centres: these heights, ...
    peg_y_hi_drop: float = 8      # ... (this far below the gate's top) ...
    peg_z: float = 41             # ... at z = +-peg_z

    # film drive: sprockets, gears, the deck, the idler (D3, D4)
    sprocket_teeth: int = 8           # one turn of a sprocket moves the film one frame (8 perforations)
    sprocket_perf: int = 6            # sprocket centres over the 7th perforation from the window's centre, each side
    tooth_h: float = 1.0              # tooth tip beyond the pitch radius (the film's mid-plane)
    tooth_base: float = 1.4           # tooth length along the film at the ring, ...
    tooth_tip: float = 0.9            # ... and at the tip; the perforation is 1.98
    tooth_w: float = 2.8              # tooth width across the film where it leaves the ring, narrowing 45 degrees each
                                      #     side to its tip: 2.2 to 2.46 where it passes the film, in a 2.79 perforation
    tooth_seat: float = 0.1           # ... it leaves the ring this far inside the ring's surface, so its foot stays in it
    ring_clear: float = 0.05          # the sprocket's rings run this far behind the film's back face
    ring_dy: float = 12.6             # ... from this far off the axis (just inside the perforations) to the film's edge
    hub_r: float = 4.5                # the sprocket between its rings, well behind the image
    shaft_d: float = 6                # sprocket shaft and idler axle
    bearing_clear: float = 0.2        # radial, in the round bearing holes
    shaft_flat: float = 0.5           # the D-flat on the top of the sprocket shaft, this deep, ...
    flat_clear: float = 0.1           # ... and the gear's D-bore this much clear of it
    pocket_clear: float = 0.4         # the sprocket's pocket in the gate body, radially beyond the tooth tips
    relief_clear: float = 0.35        # the teeth's grooves in the gate front's rear face: this deeper than the tips reach,
    relief_margin: float = 1.0        # ... and running this far past where the tips cross the face, toward the window
    shaft_floor: float = 4            # the bearing holes' floor above the table: the shaft's end stands on it
    deck_t: float = 4                 # the deck on the gate body's top: the shafts' top bearings, the idler's axle
    deck_clear: float = 0.5           # ... this far short of the CS-Lite
    gear_teeth: int = 30              # every gear, the idler too: one knob turn is one frame
    gear_pressure: float = 20         # pressure angle, degrees
    gear_t: float = 5                 # gear face width
    gear_backlash: float = 0.15       # at the pitch circle, between two meshing gears
    knob_r: float = 10                # the knob on the idler
    knob_h: float = 10
    mark_w: float = 1.2               # ... the radial groove on its top that counts turns
    mark_depth: float = 0.6
    axle_hole_depth: float = 8        # the idler's axle presses this deep into the gate body's top, ...
    axle_top_clear: float = 1         # ... and ends this far under the knob's top

    # spools (D5)
    spool_core_r: float = 15          # big enough that processed film is not curled hard
    spool_flange_r: float = 21
    spool_flange_t: float = 2
    spool_clear: float = 0.5          # each flange's inner face beyond the film's edge
    spool_gap: float = 3              # the flanges' rims this far clear of the gate's sides
    spool_pin_d: float = 6            # the dock's pins the spools turn on
    spool_slit_w: float = 1.0         # a slit in the core takes the film's end, ...
    spool_slit_depth: float = 6       # ... this deep
    cap_spigot_r: float = 8           # the cap presses its spigot into a socket in the core's top, ...
    cap_spigot_h: float = 3
    cap_t: float = 2.5                # ... the cap's flange is this thick, ...
    grip_n: int = 18                  # ... with this many scallops round its rim
    grip_r: float = 1.5
    pedestal_r: float = 8             # the dock's pedestals the spools stand on

    # light dock
    csl_clear: float = 0.5        # CS-Lite slot between the dock's lips, beyond the panel's thickness (all behind it)
    dock_extra_w: float = 26      # light dock: floor width beyond the CS-Lite's length, 13 each side (room for the spools)
    dock_margin: float = 4        # ... its floor runs this far past the spools' flanges toward the camera
    dock_tail: float = 6          # ... floor length past the slot's back edge (the back lip's front face)
    floor_t: float = 4            # ... floor thickness
    lip_h: float = 12             # ... front and back lips, above the floor, ...
    lip_t: float = 4              # ... and this thick along x; the slot between them is csl_slot
    cheek_top: float = 62         # ... side cheeks, up to this y (above the table)
    cheek_clear: float = 0.5      # ... their inner faces this far from the CS-Lite's ends
    dock_gate_clear: float = 0.2  # ... the gate sits in a notch in its floor and front lip (F10), this much clear each side

    # ---- reference solids in the assembly (not printed) ----
    film_strip_len: float = 124   # the straight run of film drawn through the gate, along z, centred on the window

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
    def gh(self) -> float:              # [GH] gate height
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
    def fit_r(self) -> float:           # adapter socket and gate front socket radius
        return self.tube_ro + self.fit_clear

    # ---- the gate ----
    @property
    def x_ref(self) -> float:          # the film reference plane: the gate front's rear face, which prints on the bed,
        return self.x_film - self.channel / 2   # and the gate body's front face; the film runs half the channel behind it

    @property
    def channel_h(self) -> float:       # the channel, along y, centred on the axis: 35.2
        return self.film_w + self.channel_clear

    @property
    def flare_scale(self) -> float:     # the light passage flares from the frame window to this times its size at the
        return 2 * self.tube_ri / math.hypot(self.win_w, self.win_h)    # tube end: its corners on the tube's bore

    @property
    def peg_points(self) -> list[tuple[float, float]]:      # (y, z) of the four friction pegs
        ys = (self.peg_y_lo, self.gh - self.peg_y_hi_drop)
        return [(y, z) for y in ys for z in (-self.peg_z, self.peg_z)]

    # ---- the film ----
    @property
    def frame_pitch(self) -> float:     # frame to frame along the film: 38, so 2 of unexposed film between frames
        return self.perfs_per_frame * self.perf_pitch

    @property
    def perf_inner(self) -> float:      # the axis to the perforations' inner edges, along y: 12.7, 0.7 past the frame
        return self.film_w / 2 - self.perf_edge - self.perf_w

    @property
    def perf_dy(self) -> float:         # the axis to each perforation row's centre line: 14.095
        return self.perf_inner + self.perf_w / 2

    @property
    def frame_zs(self) -> list[float]:  # centres of the frames wholly on the reference strip: one at z = 0, in the window,
        half = self.film_strip_len / 2 - self.frame_w / 2   # the rest every frame_pitch
        k = math.floor(half / self.frame_pitch + 1e-9)
        return [i * self.frame_pitch for i in range(-k, k + 1)]

    @property
    def perf_zs(self) -> list[float]:   # centres of each row's perforations: half a pitch either side of each frame
        half = self.perf_pitch / 2      # centre, so a frame spans 8 of them, and all wholly on the strip
        reach = self.film_strip_len / 2 - self.perf_l / 2
        j = math.floor((reach - half) / self.perf_pitch + 1e-9)
        return sorted(s * (half + i * self.perf_pitch) for s in (-1, 1) for i in range(j + 1))

    @property
    def roll_r_full(self) -> float:     # the whole roll wound on one spool
        return math.sqrt(self.spool_core_r ** 2 + self.film_roll_len * self.film_t * self.roll_pack / math.pi)

    @property
    def roll_r_half(self) -> float:     # half of it, as on each spool mid-roll (the assembly's reference rolls)
        return math.sqrt(self.spool_core_r ** 2 + self.film_roll_len * self.film_t * self.roll_pack / (2 * math.pi))

    # ---- the film drive ----
    @property
    def r_pitch(self) -> float:         # sprocket pitch radius, at the film's mid-plane: its circumference is 8 perforations
        return self.sprocket_teeth * self.perf_pitch / (2 * math.pi)

    @property
    def r_ring(self) -> float:          # the sprocket's rings, ring_clear behind the film's back face
        return self.r_pitch - self.film_t / 2 - self.ring_clear

    @property
    def r_tip(self) -> float:
        return self.r_pitch + self.tooth_h

    @property
    def r_pocket(self) -> float:        # the sprocket's pocket in the gate body
        return self.r_tip + self.pocket_clear

    @property
    def x_sprocket(self) -> float:      # the sprocket shafts and the idler, on the light side of the film
        return self.x_film + self.r_pitch

    @property
    def sprocket_z(self) -> float:      # each sprocket over a perforation's centre (D3): 30.875
        return self.perf_pitch / 2 + self.sprocket_perf * self.perf_pitch

    @property
    def tooth_sweep(self) -> float:     # half the length, along z, where the tooth tips stand past the reference plane
        return math.sqrt(self.r_tip ** 2 - (self.x_sprocket - self.x_ref) ** 2)

    @property
    def relief_depth(self) -> float:    # the grooves, forward of the reference plane
        return self.x_ref - (self.x_sprocket - self.r_tip) + self.relief_clear

    @property
    def relief_z(self) -> float:        # each groove's inner end, at its full depth; it ramps up to the face at 45 degrees
        return self.sprocket_z - self.tooth_sweep - self.relief_margin

    @property
    def gear_module(self) -> float:     # three gears in a row, centre to centre sprocket_z: m N = sprocket_z (1.029)
        return self.sprocket_z / self.gear_teeth

    @property
    def gear_r(self) -> float:          # pitch radius
        return self.gear_module * self.gear_teeth / 2

    @property
    def gear_tip_r(self) -> float:
        return self.gear_r + self.gear_module

    @property
    def gear_root_r(self) -> float:
        return self.gear_r - 1.25 * self.gear_module

    @property
    def y_deck(self) -> float:          # the deck's underside, on the gate body's top
        return self.gh

    @property
    def y_gear(self) -> float:          # every gear's underside, standing on the deck
        return self.gh + self.deck_t

    @property
    def y_shaft_top(self) -> float:     # the sprocket shafts end flush with their gears' tops
        return self.y_gear + self.gear_t

    @property
    def y_ring_lo(self) -> tuple[float, float]:     # the lower ring, y0 .. y1
        return self.axis - self.film_w / 2, self.axis - self.ring_dy

    @property
    def y_ring_hi(self) -> tuple[float, float]:     # the upper ring
        return self.axis + self.ring_dy, self.axis + self.film_w / 2

    @property
    def y_pocket(self) -> float:        # the pocket's floor: below the cone under the lower ring, pocket_clear more
        return self.y_ring_lo[0] - (self.r_ring - self.shaft_d / 2) - self.pocket_clear

    # ---- the spools ----
    @property
    def x_spool(self) -> float:         # the spools' axes, lens side of the film: a half-full roll is tangent to the film plane
        return self.x_film - (self.spool_core_r + self.roll_r_full) / 2

    @property
    def spool_z(self) -> float:         # +- this: the flanges' rims spool_gap clear of the gate's sides
        return self.gw / 2 + self.spool_gap + self.spool_flange_r

    @property
    def y_spool(self) -> float:         # the bottom flange's inner face, spool_clear below the film's lower edge
        return self.axis - self.film_w / 2 - self.spool_clear

    @property
    def spool_core_h(self) -> float:    # between the flanges
        return self.film_w + 2 * self.spool_clear

    @property
    def y_pedestal(self) -> float:      # the pedestals' tops: the spools stand on them
        return self.y_spool - self.spool_flange_t

    # ---- the dock ----
    @property
    def dock_w(self) -> float:
        return self.csl_l + self.dock_extra_w

    @property
    def dock_x0(self) -> float:         # dock_margin in front of the spools' flanges
        return self.x_spool - self.spool_flange_r - self.dock_margin

    @property
    def csl_slot(self) -> float:        # the CS-Lite's slot between the dock's lips, along x
        return self.csl_t + self.csl_clear

    @property
    def dock_x1(self) -> float:         # dock_tail past the slot's back edge
        return self.x_light + self.csl_slot + self.dock_tail


DEFAULT = Params()
