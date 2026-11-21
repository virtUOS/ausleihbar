# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Universität Osnabrück (virtUOS)

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from desksharing.serializers import validate_plan

ROOM = {"id": "r1", "type": "room", "points": [[0, 0], [100, 0], [100, 80], [0, 80]]}


def door(**kw):
    d = {"id": "d1", "type": "door", "wall": {"shape": "r1", "edge": 1, "t": 0.5},
         "width": 45, "flip_hinge": False, "flip_swing": True}
    d.update(kw)
    return d


def plan(*shapes):
    return {"shapes": list(shapes)}


class PlanValidationTests(SimpleTestCase):
    def bad(self, *shapes):
        with self.assertRaises(ValidationError):
            validate_plan(plan(*shapes))

    def test_plan_accepts_wall_bound_door_and_window(self):
        win = {"id": "w1", "type": "window", "wall": {"shape": "r1", "edge": 0, "t": 0}, "width": 60}
        p = plan(door(), win, ROOM)  # order does not matter
        self.assertEqual(validate_plan(p), p)

    def test_plan_accepts_room_outline_and_icon(self):
        p = plan({**ROOM, "outline": "wall", "icon": "wc_accessible"})
        self.assertEqual(validate_plan(p), p)
        self.bad({**ROOM, "outline": "dashed"})

    def test_plan_rejects_unknown_icon(self):
        self.bad({**ROOM, "icon": "toilet"})

    def test_plan_rejects_wall_ref_to_missing_or_non_room_shape(self):
        self.bad(door())
        self.bad(ROOM, door(wall={"shape": "nope", "edge": 0, "t": 0.5}))
        self.bad(ROOM, {"id": "l1", "type": "label", "text": "x"},
                 door(wall={"shape": "l1", "edge": 0, "t": 0.5}))
        self.bad(ROOM, {"id": "w1", "type": "window", "width": 60})

    def test_plan_rejects_edge_out_of_range_and_t_outside_0_1(self):
        for edge in (4, -1, 1.5, True, "0"):
            self.bad(ROOM, door(wall={"shape": "r1", "edge": edge, "t": 0.5}))
        for t in (-0.1, 1.1, True, "0.5", None):
            self.bad(ROOM, door(wall={"shape": "r1", "edge": 0, "t": t}))
        validate_plan(plan(ROOM, door(wall={"shape": "r1", "edge": 3, "t": 1})))

    def test_plan_rejects_non_positive_width_and_non_bool_flips(self):
        for width in (0, -5, True, "45"):
            self.bad(ROOM, door(width=width))
        self.bad(ROOM, {k: v for k, v in door().items() if k != "width"})
        self.bad(ROOM, door(flip_hinge=1))
        self.bad(ROOM, door(flip_swing="yes"))

    def test_plan_old_point_door_still_valid(self):
        p = plan({"id": "d", "type": "door", "points": [[0, 0], [30, 0]]})
        self.assertEqual(validate_plan(p), p)
