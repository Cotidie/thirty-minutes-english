import json

import pytest

from app.live.presence import Rooms, color_order


def cursor(x=0.5):
    return json.dumps({"type": "cursor", "tab": 0, "anchor": "brief", "x": x, "y": 0.5})


def view(key="chip:word:2", value=True, seq=1):
    return json.dumps({"type": "view", "key": key, "value": value, "seq": seq})


def two_people(rooms=None):
    rooms = rooms or Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for member in (mina, jo):
        member.outbox.take()
    return room, mina, jo


def test_joining_tells_me_who_is_here_and_tells_them_about_me():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    welcome = room.welcome(jo)
    assert welcome["type"] == "welcome"
    assert welcome["you"] == {"id": jo.id, "color": 1}
    assert welcome["people"] == [{"id": mina.id, "color": 0, "tab": None}]
    assert welcome["view"] == {} and welcome["timer"] is None
    assert mina.outbox.take() == [{"type": "joined", "id": jo.id, "color": 1, "tab": None}]


def test_a_cursor_and_a_tab_go_to_other_accounts_only():
    rooms = Rooms()
    room, mine = rooms.join(1, 10, 0)
    _, my_other_tab = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 1)
    for member in (mine, my_other_tab, jo):
        member.outbox.take()
    room.handle(mine, cursor())
    room.handle(mine, json.dumps({"type": "tab", "tab": 2}))
    assert my_other_tab.outbox.take() == []
    assert [m["type"] for m in jo.outbox.take()] == ["cursor", "tab"]
    assert room.welcome(my_other_tab)["people"] == [{"id": jo.id, "color": 1, "tab": None}]
    assert {"id": mine.id, "color": 0, "tab": 2} in room.welcome(jo)["people"]


def test_someone_coming_late_sees_a_cursor_that_is_standing_still():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, cursor(0.3))
    _, jo = rooms.join(1, 20, 1)
    assert [(m["type"], m["id"], m["x"]) for m in jo.outbox.take()] == [("cursor", mina.id, 0.3)]


def test_a_cursor_may_say_there_is_none():
    room, mina, jo = two_people(rooms := Rooms())
    room.handle(mina, cursor(0.3))
    room.handle(mina, json.dumps({"type": "cursor", "tab": 0, "anchor": None}))
    assert jo.outbox.take() == [{"type": "cursor", "id": mina.id, "tab": 0, "anchor": None}]
    _, late = rooms.join(1, 30, 2)
    assert late.outbox.take() == []


def test_view_goes_back_to_everyone_in_the_order_it_came_saying_who_sent_it():
    room, mina, jo = two_people()
    room.handle(mina, view(value=True, seq=1))
    room.handle(jo, view(value=False, seq=1))
    expected = [
        {"type": "view", "key": "chip:word:2", "value": True, "by": mina.id, "seq": 1},
        {"type": "view", "key": "chip:word:2", "value": False, "by": jo.id, "seq": 1},
    ]
    assert mina.outbox.take() == expected and jo.outbox.take() == expected
    assert room.welcome(mina)["view"] == {"chip:word:2": False}


def test_the_timer_goes_back_to_everyone_saying_who_sent_it():
    room, mina, jo = two_people()
    room.handle(mina, json.dumps({"type": "timer", "running": True, "elapsed": 5, "seq": 3}))
    expected = [{"type": "timer", "running": True, "elapsed": 5, "by": mina.id, "seq": 3}]
    assert mina.outbox.take() == expected and jo.outbox.take() == expected


def test_only_the_newest_cursor_of_a_person_waits_and_keeps_its_place():
    room, mina, jo = two_people()
    room.handle(mina, cursor(0.1))
    room.handle(mina, view())
    room.handle(mina, cursor(0.9))
    assert [(m["type"], m.get("x")) for m in jo.outbox.take()] == [("cursor", 0.9), ("view", None)]


def test_someone_who_left_leaves_no_cursor_behind():
    rooms = Rooms()
    room, mina, jo = two_people(rooms)
    room.handle(mina, cursor())
    rooms.leave(1, mina)
    assert jo.outbox.take() == [{"type": "left", "id": mina.id}]
    assert room.welcome(jo)["people"] == []


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"type": "shout"}',
        "x" * 1025,
        view(key="Bad Key"),
        view(key="a" * 81),
        view(value={"a": 1}),
        view(value="x" * 33),
        json.dumps({"type": "view", "key": "k", "value": True}),
        '{"type": "view", "key": "k", "value": NaN, "seq": 1}',
        '{"type": "view", "key": "k", "value": 1e999, "seq": 1}',
        cursor(2),
        json.dumps({"type": "cursor", "tab": 0, "anchor": "No Good", "x": 0.5, "y": 0.5}),
        json.dumps({"type": "cursor", "tab": 0, "anchor": "a" * 41, "x": 0.5, "y": 0.5}),
        json.dumps({"type": "cursor", "tab": 0, "anchor": "brief"}),
        json.dumps({"type": "tab", "tab": -1}),
        json.dumps({"type": "tab", "tab": 10}),
        json.dumps({"type": "tab", "tab": True}),
        json.dumps({"type": "timer", "running": True, "elapsed": -1, "seq": 1}),
        json.dumps({"type": "timer", "running": True, "elapsed": 86401, "seq": 1}),
        json.dumps({"type": "timer", "running": "yes", "elapsed": 1, "seq": 1}),
    ],
)
def test_a_bad_frame_is_dropped_and_changes_nothing(raw):
    room, mina, jo = two_people()
    before = room.welcome(jo)
    room.handle(mina, raw)
    assert jo.outbox.take() == [] and mina.outbox.take() == []
    assert room.welcome(jo) == before


def test_a_room_stops_taking_new_keys_at_2000_but_keeps_updating_old_ones():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    for i in range(2000):
        room.handle(mina, view(key=f"k:{i}"))
        mina.outbox.take()
    room.handle(mina, view(key="k:new"))
    assert mina.outbox.take() == []
    assert "k:new" not in room.welcome(mina)["view"]
    room.handle(mina, view(key="k:0", value=False))
    assert room.welcome(mina)["view"]["k:0"] is False


def test_cursors_past_40_a_second_are_dropped():
    now = [0.0]
    room, mina, jo = two_people(Rooms(clock=lambda: now[0]))
    for i in range(41):
        room.handle(mina, cursor(i / 100))
    assert [m["x"] for m in jo.outbox.take()] == [0.39]
    now[0] = 1.0
    room.handle(mina, cursor(0.9))
    assert [m["x"] for m in jo.outbox.take()] == [0.9]


def test_saying_there_is_no_cursor_is_never_dropped():
    room, mina, jo = two_people(Rooms(clock=lambda: 0.0))
    for _ in range(41):
        room.handle(mina, cursor())
    room.handle(mina, json.dumps({"type": "cursor", "tab": 0, "anchor": None}))
    assert jo.outbox.take()[-1]["anchor"] is None


def test_a_full_outbox_says_so():
    room, mina, jo = two_people()
    for i in range(256):
        room.handle(mina, view(key=f"k:{i}"))
    assert jo.outbox.overflowed is False
    room.handle(mina, view(key="k:256"))
    assert jo.outbox.overflowed is True


def test_the_room_outlives_the_last_person_by_ten_minutes():
    now = [0.0]
    rooms = Rooms(clock=lambda: now[0])
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, view())
    rooms.leave(1, mina)
    now[0] = 599.0
    room, jo = rooms.join(1, 20, 1)
    assert room.welcome(jo)["view"] == {"chip:word:2": True}
    rooms.leave(1, jo)
    now[0] = 599.0 + 601.0
    room, jo = rooms.join(1, 20, 1)
    assert room.welcome(jo)["view"] == {}


def test_the_timer_counts_on_while_running_and_stands_still_when_paused():
    now = [0.0]
    rooms = Rooms(clock=lambda: now[0])
    room, mina = rooms.join(1, 10, 0)
    room.handle(mina, json.dumps({"type": "timer", "running": True, "elapsed": 60, "seq": 1}))
    now[0] = 5.0
    assert room.welcome(mina)["timer"] == {"running": True, "elapsed": 65}
    room.handle(mina, json.dumps({"type": "timer", "running": False, "elapsed": 65, "seq": 2}))
    now[0] = 50.0
    assert room.welcome(mina)["timer"] == {"running": False, "elapsed": 65}


def test_rooms_of_different_sessions_hear_nothing_of_each_other():
    rooms = Rooms()
    room, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(2, 20, 0)
    room.handle(mina, view())
    assert jo.outbox.take() == []


def test_color_order():
    assert color_order(5, [9, 7], 5) == 0
    assert color_order(5, [9, 7], 7) == 1
    assert color_order(5, [9, 7], 9) == 2
    assert color_order(5, [9, 7], 1) == 3  # the admin, on no list
    assert color_order(None, [9, 7], 7) == 0


def test_a_taken_color_gives_way_and_a_second_connection_keeps_its_color():
    rooms = Rooms()
    _, mina = rooms.join(1, 10, 0)
    _, jo = rooms.join(1, 20, 0)
    _, mina_again = rooms.join(1, 10, 3)
    assert (mina.color, jo.color, mina_again.color) == (0, 1, 0)
