"""Derived values at the defaults match PLAN.md "Derived values" and the mockup's rail."""

import dataclasses

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
    assert (p.gw, p.gate_d, p.gate_front, p.wall) == (92, 30, 14, 3)
    assert (p.win_w, p.win_h, p.gap) == (38, 26, 25)
    assert (p.front_wall, p.fit_clear, p.plate_t, p.wedge_gap) == (4, 0.3, 1.8, 0.9)
    assert p.gate_above_axis == 36
    assert (p.channel, p.sw_travel) == (0.6, 10)
    assert (p.ramp_len, p.ramp_min, p.ramp_rise) == (12, 0.1, 0.7)
    assert (p.film_w, p.film_t, p.frame_w, p.frame_h) == (35, 0.13, 36, 24)
    assert (p.lens_len, p.lens_r) == (125, 37)
    assert (p.csl_l, p.csl_h, p.csl_t, p.csl_lit_w, p.csl_lit_h) == (165, 112, 20, 149, 95)
    assert (p.bed_x, p.bed_y) == (220, 220)


def test_fit_clearances_for_the_drop_in_and_sliding_parts():
    p = DEFAULT
    assert (p.plate_clear, p.lid_clear, p.csl_clear) == (0.25, 0.2, 0.5)
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
    assert p.dock_w == 181
    assert p.dock_x0 == 271
    assert p.dock_x1 == 306.5
    assert p.dock_x1 - p.dock_x0 == 35.5


def test_lock_mechanism_x_stations():
    p = DEFAULT
    assert p.x_pp == pytest.approx(257.1)
    assert p.x_wedge == pytest.approx(258.0)
    assert p.x_knob == pytest.approx(259.0)


def test_ramp_thickness():
    p = DEFAULT
    assert p.ramp_t(-6) == pytest.approx(0.8)
    assert p.ramp_t(6) == pytest.approx(0.1)
    assert p.ramp_t(0) == pytest.approx(0.45)


def test_lock_shift_and_preload():
    p = DEFAULT
    # unclamped travel is 0.5833, so the film limit (channel - film_t = 0.47) governs
    assert p.clamp_shift(5) == pytest.approx(0.47)
    assert p.lock_shift == pytest.approx(0.47)
    assert p.clamp_shift(-5) == pytest.approx(0.0)  # knob at SLIDE: the plate has not moved
    assert p.preload == pytest.approx(0.1133333, abs=1e-6)


def test_pad_thickness():
    assert DEFAULT.pad_t == pytest.approx(0.7416667, abs=1e-6)


def test_tube_len_tracks_wd():
    p = Params(wd=150)
    assert p.tube_len == p.wd - 13 == 137
    assert p.x_film == 275
    assert p.dock_x1 - p.dock_x0 == 35.5


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


def test_the_film_slot_starts_at_the_front_plates_front_face():
    p = DEFAULT
    assert p.x_front_plate == pytest.approx(p.x_film - p.channel / 2 - p.plate_t) == pytest.approx(252.9)
    assert p.film_slot_x0 == p.x_front_plate
