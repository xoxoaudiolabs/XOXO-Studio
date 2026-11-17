"""Tests for the Studio's sequencer (sequencer.py): eight MIDI tracks, 64 steps, songs cleaned (older ones read:
XO-4's, and with pads tracks), steps on the grid, tracks of their own lengths, swing, pattern changes on the bar,
each track's notes on its channel, the process on time.

  python tests/test_sequencer.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))

import sequencer  # noqa: E402

RATE = 48000
PER = 60.0 / (120 * 24)                     # a clock tick at 120 BPM
U = PER * 6                                 # a 16th: 0.125 s
MIDI, OTHER = 1, 5                          # tracks 2 and 6: MIDI channels 2 and 6 in a new song


def song_with(track, steps, length=16, pattern="A"):
    song = sequencer.empty_song()
    song["patterns"][pattern][track]["len"] = length
    for i, step in steps.items():
        song["patterns"][pattern][track]["steps"][i] = step
    return sequencer.clean_song(song)


def playing(seq, origin=10.0):
    seq.grid = (PER, origin, True)
    return seq


def test_eight_tracks_and_64_steps():
    """a new song: eight MIDI tracks on channels 1-8; patterns A-H; 64 steps a track"""
    song = sequencer.empty_song()
    assert sequencer.NTRACK == 8 and sequencer.NSTEP == 64
    assert [t["channel"] for t in song["tracks"]] == list(range(8)) and all("kind" not in t for t in song["tracks"])
    assert sorted(song["patterns"]) == list(sequencer.PATTERNS)
    assert all(len(tracks) == 8 and all(len(t["steps"]) == 64 for t in tracks) for tracks in song["patterns"].values())
    long = song_with(MIDI, {63: {"notes": [60]}}, length=64)
    seq = playing(sequencer.Sequencer())
    ons = [round((t - 10.0) / U) for t, _, k, _, _ in seq.due(long, seq.ahead, 10.0, 10.0 + 65 * U) if k == "on"]
    assert ons == [63]                                                  # step 64: the 64th 16th


def test_clean_song():
    """anything -> a whole song: steps cleaned, values in range, channels checked"""
    s = sequencer.clean_song({"patterns": {"A": [{"len": 99, "steps": [{"notes": [3, 3, 200, "x"], "vel": 300}]}]},
                              "pattern": "Q", "swing": 500,
                              "tracks": [{}, {"channel": 40, "level": 5}, {"channel": -2}]})
    first = s["patterns"]["A"][0]
    assert first["len"] == 64 and first["steps"][0] == {"notes": [3], "vel": 127, "len": 1.0, "nudge": 0}
    assert s["pattern"] == "A" and s["swing"] == 100
    assert s["tracks"][1] == {"channel": 15, "level": 2.0} and s["tracks"][2]["channel"] == 0
    chord = sequencer.clean_step({"notes": [60, 64, 67, 71, 74]})
    assert chord["notes"] == [60, 64, 67, 71]                           # four at most: a chord
    assert sequencer.clean_step({"notes": []}) is None and sequencer.clean_song(None) == sequencer.empty_song()


def test_an_xo4_song_is_read():
    """a song saved when this was XO-4's (four tracks, "patches", "midi_channel", "levels"): its drums track 1 on
    channel 10 (each pad its note: 36 + pad, the hit's level its velocity), its MIDI track 2 on its channel, the
    synth tracks' notes tracks 3 and 4 on the next channels"""
    old = {"patterns": {"A": [{"len": 16, "steps": [{"notes": [1, 3], "levels": [3, 1]}]},
                              {"len": 8, "steps": [{"notes": [60]}]},
                              {"len": 4, "steps": [{"notes": [36]}]}, {"len": 32, "steps": [None, {"notes": [48]}]}]},
           "patches": [{"ratio": 2.0}, {}], "midi_channel": 3, "levels": [1.0, 0.5, 0.6, 0.8], "pattern": "A"}
    s = sequencer.clean_song(old)
    assert [(t["channel"], t["level"]) for t in s["tracks"][:4]] == [(9, 1.0), (3, 0.8), (4, 0.5), (5, 0.6)]
    a = s["patterns"]["A"]
    assert a[0]["steps"][0]["notes"] == [37, 39] and a[0]["steps"][0]["vel"] == 127     # (HARD: the loudest)
    assert a[1]["len"] == 32 and a[1]["steps"][1]["notes"] == [48]
    assert a[2]["steps"][0]["notes"] == [60] and a[3]["steps"][0]["notes"] == [36] and "patches" not in s


def test_a_song_with_a_pads_track_is_read():
    """a song from when a track could play the pads: that track is MIDI on channel 10, its hits notes 36-51 (the
    pads, through the route SEQ > SMP)"""
    song = {"tracks": [{"kind": "pads", "channel": 9}, {"kind": "midi", "channel": 2}],
            "patterns": {"A": [{"len": 16, "steps": [{"notes": [0, 15], "levels": [1, 2]}]},
                               {"len": 16, "steps": [{"notes": [60]}]}]}}
    s = sequencer.clean_song(song)
    assert s["tracks"][0] == {"channel": 9, "level": 1.0} and s["tracks"][1]["channel"] == 2
    assert s["patterns"]["A"][0]["steps"][0]["notes"] == [36, 51] and s["patterns"]["A"][1]["steps"][0]["notes"] == [60]


def test_steps_on_the_grid():
    """a step sounds at tick 0 + its number of 16ths, its note off at GATE of its length"""
    song = song_with(MIDI, {0: {"notes": [60]}, 4: {"notes": [64], "len": 2}})
    seq = playing(sequencer.Sequencer())
    notes = seq.due(song, seq.ahead, 10.0, 10.0 + 16 * U)
    assert [(round(t - 10.0, 4), kind, note) for t, _, kind, note, _ in notes] == [
        (0.0, "on", 60), (round(U * sequencer.GATE, 4), "off", 60), (round(4 * U, 4), "on", 64),
        (round(4 * U + 2 * U * sequencer.GATE, 4), "off", 64)]


def test_own_lengths_and_swing():
    """a 3-step track comes round every 3 steps, a 16-step one every 16; swing delays the odd 16ths"""
    song = song_with(MIDI, {0: {"notes": [60]}}, length=3)
    seq = playing(sequencer.Sequencer())
    ons = [round((t - 10.0) / U, 3) for t, _, kind, _, _ in seq.due(song, seq.ahead, 10.0, 10.0 + 12 * U)
           if kind == "on"]
    assert ons == [0, 3, 6, 9]
    song = song_with(MIDI, {0: {"notes": [60]}, 1: {"notes": [62]}})
    song["swing"] = 50
    seq = playing(sequencer.Sequencer())
    ons = [round((t - 10.0) / U, 3) for t, _, kind, _, _ in seq.due(song, seq.ahead, 10.0, 10.0 + 2 * U)
           if kind == "on"]
    assert ons == [0, 1.25]                                              # 50: a quarter of a 16th late


def test_pattern_changes_on_the_bar():
    """a pattern picked while playing starts on the next bar, for every track; stopped, at once"""
    song = song_with(MIDI, {0: {"notes": [60]}})
    song["patterns"]["B"][MIDI]["steps"][0] = {"notes": [72], "vel": 100, "len": 1.0}
    seq = playing(sequencer.Sequencer())
    seq.due(song, seq.now, 10.0, 10.0 + 4 * U)                          # into the first bar
    seq.due(song, seq.ahead, 10.0, 10.0 + 4 * U)
    seq.pick(song, "B")
    assert seq.queued == "B" and song["pattern"] == "A"
    notes = seq.due(song, seq.ahead, 10.0 + 4 * U, 10.0 + 17 * U)
    seq.due(song, seq.now, 10.0 + 4 * U, 10.0 + 17 * U)
    assert [n for _, _, k, n, _ in notes if k == "on"] == [72] and song["pattern"] == "B" and seq.queued is None
    stopped = sequencer.Sequencer()
    stopped.pick(song, "C")
    assert song["pattern"] == "C"


def test_stop_lets_go():
    """stopping ends the notes held"""
    song = song_with(MIDI, {0: {"notes": [48], "len": 8}})
    seq = playing(sequencer.Sequencer())
    assert [k for _, _, k, _, _ in seq.due(song, seq.ahead, 10.0, 10.0 + U)] == ["on"]
    seq.grid = (PER, None, False)
    assert [(k, n) for _, _, k, n, _ in seq.due(song, seq.ahead, 11.0, 11.1)] == [("off", 48)]
    assert seq.due(song, seq.ahead, 11.1, 11.2) == []


def test_each_track_goes_out_ahead_on_its_channel():
    """the notes are handed out LOOKAHEAD early, with the time each is to sound, each track on its own channel at
    its level"""
    song = song_with(MIDI, {0: {"notes": [36], "vel": 90, "len": 1.0}})
    song["patterns"]["A"][OTHER]["steps"][0] = {"notes": [72], "vel": 64, "len": 1.0}
    song["tracks"][MIDI]["channel"], song["tracks"][OTHER]["channel"], song["tracks"][OTHER]["level"] = 9, 3, 0.5
    engine = sequencer.Engine(RATE)
    engine.set_song(song)
    engine.seq.grid = (PER, 10.0, True)
    ahead = engine.step(512, 10.0 - sequencer.LOOKAHEAD)                 # the block before step 0 is heard
    midi = sorted(sequencer.midi_notes(ahead, engine.song))
    assert midi == [(10.0, [0x93, 72, 32]), (10.0, [0x99, 36, 90])]


def test_midi_tracks_through_the_routes():
    """SEQ is a source in the MIDI routes: on to the USB gear, off to Bluetooth, the network and the pads"""
    import blemidi
    assert "SEQ" in blemidi.SOURCES
    for dest, on in (("USB", True), ("BT", False), ("NET", False), ("SMP", False)):
        assert blemidi.route_default(f"SEQ>{dest}")["on"] is on, dest
    bridge = blemidi.MidiBridge()
    sent = []
    bridge.deliver = lambda key, messages: sent.append((key, messages))
    bridge.route_from("SEQ", bytes([0x90, 36, 90]))
    assert ("USB", [bytes([0x90, 36, 90])]) in [(k.split(">")[1], m) for k, m in sent if m]
    assert bridge.source_label("SEQ") == "Sequencer"


def test_engine_steps_through():
    """the engine steps the time through: the playhead moves, the pattern changes on the bar, notes go out"""
    engine = sequencer.Engine(RATE)
    song = song_with(0, {0: {"notes": [38], "vel": 100, "len": 1}})
    song["patterns"]["A"][MIDI]["steps"][4] = {"notes": [60], "vel": 90, "len": 1}
    engine.set_song(song)
    engine.seq.grid = (PER, 10.0, True)
    notes, t = [], 10.0
    while t < 10.0 + 16 * U:
        notes += engine.step(512, t)
        t += 512 / RATE
    assert {n[1] for n in notes} == {0, MIDI}
    assert sorted(m[1][:2] for m in sequencer.midi_notes(notes, engine.song)) == [[0x80, 38], [0x81, 60],
                                                                                   [0x90, 38], [0x91, 60]]
    assert engine.seq.step is not None
    engine.seq.pick(engine.song, "B")
    while t < 10.0 + 33 * U:
        engine.step(512, t)
        t += 512 / RATE
    assert engine.song["pattern"] == "B"


def test_sequencer_process():
    """the sequencer's loop (run) in a thread: the song and the grid in, the tracks' notes to the MIDI process, the
    step to the app; on time"""
    import multiprocessing
    import threading
    import time
    app, child = multiprocessing.Pipe()
    grid_in, grid_out = multiprocessing.Pipe(duplex=False)
    notes_in, notes_out = multiprocessing.Pipe(duplex=False)
    threading.Thread(target=sequencer.run, args=(child, grid_in, notes_out, RATE), daemon=True).start()
    song = song_with(MIDI, {i: {"notes": [48], "vel": 100, "len": 0.5} for i in range(16)})
    app.send(("song", song))
    start = time.monotonic()
    grid_out.send(("grid", PER, start, True))
    ons, early = [], []
    while time.monotonic() < start + 1.2 and len(ons) < 4:
        if notes_in.poll(0.05):
            msg = notes_in.recv()
            assert msg[0] == "seq"
            got = [n for n in msg[1] if n[1][0] & 0xF0 == 0x90]
            early += [n[0] - time.monotonic() for n in got]
            ons += got
    assert len(ons) >= 4 and all(n[1][:2] == [0x91, 48] for n in ons)
    steps = [(n[0] - start) / U for n in ons]
    assert all(abs(x - round(x)) < 0.01 for x in steps), steps        # on the grid's 16ths
    assert [round(b - a) for a, b in zip(steps, steps[1:])] == [1] * (len(steps) - 1)   # none missed
    assert min(early) > 0                                             # each sent before it's to be heard
    assert app.poll(1.0) and app.recv()[0] in ("step", "pattern")


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
