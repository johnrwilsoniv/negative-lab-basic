"""Derived values at the defaults match PLAN.md "Derived values", the mockup's rail, and the film transport (D1-D5)."""

import dataclasses
import math

import pytest

from params import DEFAULT, Params


def test_default_is_a_params_with_the_user_inputs():
    assert isinstance(DEFAULT, Params)
    assert (DEFAULT.wd, DEFAULT.axis) == (130, 42.5)


def test_params_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT.wd = 150  # type: ignore[misc]


def test_callers_vary_inputs_by_constructing():
    p = Params(wd=150, axis=40)
    assert (p.wd, p.axis) == (150, 40)
    assert DEFAULT.wd == 130


def test_plan_constants():
    p = DEFAULT
    assert (p.thread_major, p.thread_pitch, p.thread_len) == (67, 0.75, 4.5)
    assert p.thread_clear == 0.15
    assert (p.adapter_r, p.adapter_bore_r, p.socket_depth, p.flange) == (39, 31, 9, 3)
    assert (p.tube_ro, p.tube_ri) == (36, 32)
    assert (p.gw, p.gate_d, p.gate_front) == (92, 39, 14)     # gate_d = gate_front + gap (F10)
    assert (p.win_w, p.win_h, p.win_depth, p.gap) == (38, 26, 1.8, 25)
    assert (p.front_wall, p.fit_clear, p.gate_above_axis) == (4, 0.3, 36)
    assert (p.film_w, p.film_t, p.frame_w, p.frame_h) == (35, 0.13, 36, 24)
    assert (p.lens_len, p.lens_r) == (125, 37)
    assert (p.csl_l, p.csl_h, p.csl_t, p.csl_lit_w, p.csl_lit_h) == (165, 112, 20, 149, 95)
    assert (p.bed_x, p.bed_y) == (220, 220)


def test_the_channel_is_fixed_and_the_film_runs_in_its_middle():
    p = DEFAULT
    assert (p.channel, p.channel_clear) == (0.3, 0.2)
    assert p.x_ref == pytest.approx(254.85)                # the gate front's rear face and the gate body's front face
    assert p.x_ref + p.channel / 2 == pytest.approx(p.x_film)
    assert p.channel_h == pytest.approx(35.2)
    assert p.channel - p.film_t == pytest.approx(0.17)      # the film's play front to back


def test_fit_clearances():
    p = DEFAULT
    assert (p.bearing_clear, p.flat_clear, p.pocket_clear, p.ring_clear) == (0.2, 0.1, 0.4, 0.05)
    assert (p.peg_fit, p.spool_clear, p.csl_clear, p.dock_gate_clear) == (0, 0.5, 0.5, 0.2)
    assert p.csl_slot == 20.5                         # the CS-Lite's slot between the dock's lips


def test_thread_profile():
    # ISO 68-1 external thread M67 x 0.75, then moved inward by the FDM clearance
    p = DEFAULT
    assert p.thread_h == pytest.approx(0.866 * 0.75, abs=1e-4)
    assert p.thread_crest_r == pytest.approx(67 / 2 - 0.15)
    assert p.thread_root_r == pytest.approx((67 - 1.226869 * 0.75) / 2 - 0.15, abs=1e-6)   # d3 = 66.08
    assert p.thread_crest_flat == pytest.approx(0.75 / 8)
    assert (p.thread_lead_in, p.coupon_grip) == (45, 2)


def test_rail_values_at_defaults():
    p = DEFAULT
    assert p.x_front == 125
    assert p.x_film == 255
    assert p.x_gate == 241
    assert p.x_light == 280
    assert p.gh == pytest.approx(78.5)
    assert p.tube_x0 == 128
    assert p.tube_x1 == 245
    assert p.tube_len == 117
    assert p.fit_r == pytest.approx(36.3)
    assert p.dock_w == 191                            # 13 each side of the panel, for the spools
    assert p.dock_x1 == 306.5


def test_tube_len_tracks_wd():
    p = Params(wd=150)
    assert p.tube_len == p.wd - 13 == 137
    assert p.x_film == 275
    assert p.dock_x1 - p.dock_x0 == pytest.approx(DEFAULT.dock_x1 - DEFAULT.dock_x0)     # the dock moves, whole


def test_the_sprocket_is_a_pinion_on_the_film_one_turn_a_frame():
    p = DEFAULT
    assert p.sprocket_teeth == p.perfs_per_frame == 8
    assert 2 * math.pi * p.r_pitch == pytest.approx(p.frame_pitch)
    assert p.r_pitch == pytest.approx(6.0479, abs=1e-4)
    assert p.x_sprocket == pytest.approx(p.x_film + p.r_pitch)
    assert p.r_ring == pytest.approx(p.r_pitch - p.film_t / 2 - p.ring_clear)
    assert p.r_tip == pytest.approx(p.r_pitch + 1)
    assert p.r_pocket == pytest.approx(p.r_tip + 0.4)


def test_each_sprocket_sits_over_a_perforation_outside_the_light():
    p = DEFAULT
    assert p.sprocket_z == pytest.approx(30.875)
    assert p.sprocket_z in p.perf_zs
    # its pocket stays outside the body's light passage, which widens from 20 to 23 half-width front to back
    widest = p.body_win_w / 2 + (p.rear_win_w - p.body_win_w) / 2 * (p.r_pitch / p.gap)
    assert p.sprocket_z - p.r_pocket > widest + 2
    assert p.perf_dy == pytest.approx(14.095)


def test_three_equal_gears_in_a_row_between_the_sprockets():
    p = DEFAULT
    assert p.gear_teeth == 30 and p.gear_teeth % 2 == 0      # even: the idler shows each gear a gap (D4)
    assert p.gear_module * p.gear_teeth == pytest.approx(p.sprocket_z)
    assert 2 * p.gear_r == pytest.approx(p.sprocket_z)       # two pitch radii, centre to centre
    assert p.gear_tip_r == pytest.approx(p.gear_r + p.gear_module)
    assert p.gear_root_r == pytest.approx(p.gear_r - 1.25 * p.gear_module)
    assert p.x_sprocket + p.gear_tip_r < p.x_light - 2      # clear of the CS-Lite, which stands 112 tall


def test_the_drive_stack_on_the_gate():
    p = DEFAULT
    assert (p.y_deck, p.y_gear, p.y_shaft_top) == pytest.approx((78.5, 82.5, 87.5))
    assert p.y_ring_lo == pytest.approx((25, 29.9)) and p.y_ring_hi == pytest.approx((55.1, 60))
    assert p.y_ring_lo[1] - p.axis == pytest.approx(-p.ring_dy) and p.ring_dy < p.perf_inner     # just inside the perforations,
    assert p.ring_dy > p.frame_h / 2                                                # outside the frame
    assert p.y_pocket == pytest.approx(25 - (p.r_ring - 3) - 0.4)


def test_the_tooth_grooves_in_the_gate_front():
    p = DEFAULT
    assert p.relief_depth == pytest.approx(p.x_ref - (p.x_sprocket - p.r_tip) + 0.35)
    assert p.relief_depth == pytest.approx(1.2, abs=1e-3)
    assert p.tooth_sweep == pytest.approx(math.sqrt(p.r_tip ** 2 - (p.x_sprocket - p.x_ref) ** 2))
    assert p.relief_z - p.relief_depth > p.win_w / 2       # the grooves' ramps end outside the frame window


def test_the_rolls_and_the_spools():
    p = DEFAULT
    assert p.roll_r_full == pytest.approx(math.sqrt(15 ** 2 + 1600 * 0.13 * 1.15 / math.pi))
    assert p.roll_r_full < p.spool_flange_r - 3            # a whole roll fits with room to spare
    assert p.roll_r_half ** 2 - 15 ** 2 == pytest.approx((p.roll_r_full ** 2 - 15 ** 2) / 2)
    assert p.x_spool == pytest.approx(p.x_film - (p.spool_core_r + p.roll_r_full) / 2)
    assert p.spool_z == pytest.approx(70)                  # flanges 3 clear of the gate's sides
    assert p.y_spool == pytest.approx(p.axis - 17.5 - 0.5) and p.spool_core_h == pytest.approx(36)
    assert p.y_pedestal == pytest.approx(p.y_spool - p.spool_flange_t)
    assert p.dock_x0 == pytest.approx(p.x_spool - p.spool_flange_r - p.dock_margin)
    assert p.spool_z + p.spool_flange_r < p.dock_w / 2     # the spools stand on the dock


def test_baffles():
    p = DEFAULT
    assert (p.baffle_h, p.baffle_pitch, p.baffle_margin) == (1, 8, 2)
    assert p.tube_ri - p.baffle_h == p.adapter_bore_r     # the ribs never close in past the adapter bore
    assert p.baffle_count == 15                           # (117 - 2*2 - 1) / 8 -> 14 pitches, 15 ribs
    assert Params(wd=150).baffle_count == 17              # (137 - 4 - 1) / 8 = 16.5 -> 16 pitches
    assert Params(baffle_h=0).baffle_count == 0


def test_tube_max_len_follows_the_smaller_bed_side():
    assert DEFAULT.tube_max_len == 220
    assert Params(bed_x=200).tube_max_len == 200


def test_gate_height_tracks_axis():
    assert Params(axis=50).gh == pytest.approx(86)


def test_the_lowest_axis_is_the_adapters_radius():
    assert DEFAULT.axis_min == DEFAULT.adapter_r == 39
    assert Params(axis=39).axis == 39                 # the adapter just reaches the table
    assert Params(adapter_r=35, axis=36).axis_min == 35       # follows adapter_r, not a literal


@pytest.mark.parametrize("axis", [38.99, 35, 30, 0])
def test_an_axis_too_low_for_the_adapter_is_refused_naming_the_minimum(axis):
    with pytest.raises(ValueError, match="adapter") as err:
        Params(axis=axis)
    message = str(err.value)
    assert "table" in message and "39" in message
    assert "\n" not in message                        # one line, for the command line


def test_a_bigger_adapter_raises_the_minimum():
    with pytest.raises(ValueError, match="adapter"):
        Params(adapter_r=45)                          # the default axis 42.5 is now too low


def test_the_peg_points_are_outside_the_channel_and_the_pockets():
    p = DEFAULT
    assert p.peg_points == [(10, -41), (10, 41), (pytest.approx(70.5), -41), (pytest.approx(70.5), 41)]
    for y, z in p.peg_points:
        assert not (p.axis - p.channel_h / 2 - p.peg_d / 2 < y < p.axis + p.channel_h / 2 + p.peg_d / 2)
        assert abs(z) - p.peg_d / 2 > p.sprocket_z + p.r_pocket / math.sqrt(2)


def test_ks_perforations_and_frame_pitch():
    p = Params()
    assert (p.perf_pitch, p.perf_l, p.perf_w, p.perf_r, p.perf_edge) == (4.75, 1.98, 2.79, 0.5, 2.01)
    assert p.frame_pitch == pytest.approx(38)
    assert p.perf_inner == pytest.approx(12.7)          # 0.7 clear of the 24 frame's edge


def test_the_strip_holds_three_frames_one_centred_on_the_window():
    p = Params()
    assert p.frame_zs == pytest.approx([-38, 0, 38])
    zs = p.perf_zs
    assert len(zs) == 26
    assert zs[0] == pytest.approx(-59.375) and zs[-1] == pytest.approx(59.375)
    assert all(b - a == pytest.approx(4.75) for a, b in zip(zs, zs[1:]))
    assert sum(1 for z in zs if -18 < z < 18) == 8      # 8 perforations a frame, symmetric about its centre


def test_frames_and_perforations_stay_on_a_shorter_strip():
    p = Params(film_strip_len=100)
    assert p.frame_zs == pytest.approx([0])
    assert min(p.perf_zs) - p.perf_l / 2 >= -50 and max(p.perf_zs) + p.perf_l / 2 <= 50
