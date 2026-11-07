"""Tests for XO-4's engine (xo4.py): songs cleaned, steps on the grid, tracks of their own lengths, swing, pattern
changes on the bar, the synths played on their frame, the drums' hits for the pads, the MIDI track's notes.

  python tests/test_xo4.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))

import xo4  # noqa: E402

RATE = 48000
PER = 60.0 / (120 * 24)                     # a clock tick at 120 BPM
U = PER * 6                                 # a 16th: 0.125 s


def song_with(track, steps, length=16, pattern="A"):
    song = xo4.empty_song()
    song["patterns"][pattern][track]["len"] = length
    for i, step in steps.items():
        song["patterns"][pattern][track]["steps"][i] = step
    return xo4.clean_song(song)


def playing(seq, origin=10.0):
    seq.grid = (PER, origin, True)
    return seq


def test_clean_song():
    """anything -> a whole song: eight patterns of four tracks, steps cleaned, values in range"""
    s = xo4.clean_song({"patterns": {"A": [{"len": 99, "steps": [{"notes": [3, 3, 20, "x"], "vel": 300}]}]},
                        "pattern": "Q", "swing": 500, "levels": [5, -1], "midi_channel": 40,
                        "patches": [{"ratio": 99}, "nonsense"]})
    assert sorted(s["patterns"]) == list(xo4.PATTERNS) and all(len(t) == 4 for t in s["patterns"].values())
    drums = s["patterns"]["A"][xo4.DRUMS]
    assert drums["len"] == 64 and drums["steps"][0] == {"notes": [3], "vel": 127, "len": 1.0, "nudge": 0,
                                                        "levels": [0], "ratchets": [1]}       # pad 20: no pad
    assert s["pattern"] == "A" and s["swing"] == 100 and s["levels"][:2] == [2.0, 0.0] and s["midi_channel"] == 15
    assert s["patches"][0]["ratio"] == 16.0 and s["patches"][1]["ratio"] == xo4.SYNTH_PATCHES[1]["ratio"]
    synth = xo4.clean_step({"notes": [60, 64, 67, 71, 74]}, xo4.SYNTH1)
    assert synth["notes"] == [60, 64, 67, 71]                           # four at most: a chord
    assert xo4.clean_step({"notes": []}, xo4.SYNTH1) is None and xo4.clean_song(None) == xo4.empty_song()


def test_steps_on_the_grid():
    """a step sounds at tick 0 + its number of 16ths, its note off at GATE of its length"""
    song = song_with(xo4.SYNTH1, {0: {"notes": [60]}, 4: {"notes": [64], "len": 2}})
    seq = playing(xo4.Sequencer())
    notes = seq.due(song, seq.now, 10.0, 10.0 + 16 * U)
    assert [(round(t - 10.0, 4), kind, note) for t, _, kind, note, _ in notes] == [
        (0.0, "on", 60), (round(U * xo4.GATE, 4), "off", 60), (round(4 * U, 4), "on", 64),
        (round(4 * U + 2 * U * xo4.GATE, 4), "off", 64)]


def test_own_lengths_and_swing():
    """a 3-step track comes round every 3 steps, a 16-step one every 16; swing delays the odd 16ths"""
    song = song_with(xo4.SYNTH1, {0: {"notes": [60]}}, length=3)
    seq = playing(xo4.Sequencer())
    ons = [round((t - 10.0) / U, 3) for t, _, kind, _, _ in seq.due(song, seq.now, 10.0, 10.0 + 12 * U)
           if kind == "on"]
    assert ons == [0, 3, 6, 9]
    song = song_with(xo4.SYNTH1, {0: {"notes": [60]}, 1: {"notes": [62]}})
    song["swing"] = 50
    seq = playing(xo4.Sequencer())
    ons = [round((t - 10.0) / U, 3) for t, _, kind, _, _ in seq.due(song, seq.now, 10.0, 10.0 + 2 * U)
           if kind == "on"]
    assert ons == [0, 1.25]                                              # 50: a quarter of a 16th late


def test_pattern_changes_on_the_bar():
    """a pattern picked while playing starts on the next bar, for every track; stopped, at once"""
    song = song_with(xo4.SYNTH1, {0: {"notes": [60]}})
    song["patterns"]["B"][xo4.SYNTH1]["steps"][0] = {"notes": [72], "vel": 100, "len": 1.0}
    seq = playing(xo4.Sequencer())
    seq.due(song, seq.now, 10.0, 10.0 + 4 * U)                          # into the first bar
    seq.pick(song, "B")
    assert seq.queued == "B" and song["pattern"] == "A"
    notes = seq.due(song, seq.now, 10.0 + 4 * U, 10.0 + 17 * U)
    assert [n for _, _, k, n, _ in notes if k == "on"] == [72] and song["pattern"] == "B" and seq.queued is None
    stopped = xo4.Sequencer()
    stopped.pick(song, "C")
    assert song["pattern"] == "C"


def test_stop_lets_go():
    """stopping ends what's held: the synths' notes and the drums' and MIDI's"""
    song = song_with(xo4.MIDI, {0: {"notes": [48], "len": 8}})
    seq = playing(xo4.Sequencer())
    assert [k for _, _, k, _, _ in seq.due(song, seq.ahead, 10.0, 10.0 + U)] == ["on"]
    seq.grid = (PER, None, False)
    assert [(k, n) for _, _, k, n, _ in seq.due(song, seq.ahead, 11.0, 11.1)] == [("off", 48)]
    assert seq.due(song, seq.ahead, 11.1, 11.2) == []


def test_engine_plays_the_synths_on_their_frame():
    """a synth step starts on its own frame within a block: silence before it, sound from it"""
    import numpy as np
    engine = xo4.Engine(RATE)
    engine.set_song(song_with(xo4.SYNTH1, {1: {"notes": [69], "vel": 127}}))
    engine.seq.grid = (PER, 10.0, True)
    t0 = 10.0 + U - 256 / RATE                                           # step 1 falls 256 frames into the block
    out, ahead = engine.render(512, t0)
    assert out.shape == (512, 2) and np.abs(out[:255]).max() == 0 and np.abs(out[256:]).max() > 0
    assert ahead == [] and engine.sounding()[0] == [69]


def test_drums_and_midi_go_out_ahead():
    """the drums' and MIDI's notes are handed out LOOKAHEAD early, with the time each is to sound"""
    song = song_with(xo4.DRUMS, {0: {"notes": [0, 4], "vel": 100}})
    song["patterns"]["A"][xo4.MIDI]["steps"][0] = {"notes": [36], "vel": 90, "len": 1.0}
    song["midi_channel"], song["levels"][xo4.DRUMS] = 9, 0.5
    engine = xo4.Engine(RATE)
    engine.set_song(song)
    engine.seq.grid = (PER, 10.0, True)
    _, ahead = engine.render(512, 10.0 - xo4.LOOKAHEAD)                  # the block before step 0 is heard
    hits = xo4.drum_hits(ahead, engine.song["levels"])
    assert [(round(t, 4), k, pad, v) for t, k, pad, v in hits if k == "on"] == [(10.0, "on", 0, 50),
                                                                              (10.0, "on", 4, 50)]
    midi = xo4.midi_notes(ahead, engine.song["midi_channel"], engine.song["levels"][xo4.MIDI])
    assert midi == [(10.0, [0x99, 36, 90])]


def test_pads_take_the_hits():
    """the pad process plays XO-4's drums: queued while playing (each at its time), dropped when stopped"""
    import pads
    seq = pads.Sequencer()
    seq.queue([(10.5, "on", 2, 100)])
    assert seq.pending == []                                             # stopped: nothing kept
    seq.grid = (PER, 10.0, True)
    seq.queue([(10.5, "on", 2, 100), (10.6, "off", 2, 0), (10.5, "on", 99, 100)])
    kit = pads.empty_kit()
    assert seq.events(kit["seq"], 10.4, 10.55) == [(10.5, "on", 2, 100)]
    seq.grid = (PER, None, False)
    assert seq.events(kit["seq"], 11.0, 11.1) == [(11.0, "off", 2, 0)] and seq.pending == []


def test_midi_track_through_the_routes():
    """XO4 is a source in the MIDI routes: on to the USB gear, off to Bluetooth, the network and the pads"""
    import blemidi
    assert "XO4" in blemidi.SOURCES
    for dest, on in (("USB", True), ("BT", False), ("NET", False), ("SMP", False)):
        assert blemidi.route_default(f"XO4>{dest}")["on"] is on, dest
    bridge = blemidi.MidiBridge()
    sent = []
    bridge.deliver = lambda key, messages: sent.append((key, messages))
    bridge.route_from("XO4", bytes([0x90, 36, 90]))
    assert ("USB", [bytes([0x90, 36, 90])]) in [(k.split(">")[1], m) for k, m in sent if m]
    assert bridge.source_label("XO4") == "XO-4"


def test_sound_settings():
    """the SOUND page's steps: through a list of values from the nearest, or by a step in a range; how values
    read; every starting sound a whole, clean patch"""
    assert xo4.step_setting("ratio", 2.0, 1) == 2.5 and xo4.step_setting("ratio", 1.9, -1) == 1.5
    assert xo4.step_setting("ratio", 16.0, 4) == 16.0 and xo4.step_setting("ratio", 0.25, -1) == 0.25   # the ends
    assert xo4.step_setting("index", 3.0, 4) == 4.0 and xo4.step_setting("level", 0.99, 1) == 1.0
    assert xo4.step_setting("attack", 0.0, 1) == 0.002 and xo4.step_setting("sustain", 0.6, -2) == 0.5
    assert [xo4.setting_text(k, v) for k, v in (("release", 0.25), ("release", 1.5), ("level", 0.22),
                                                ("ratio", 1.41))] == ["250MS", "1.5S", "22%", "1.41"]
    import xo4synth
    for name, patch in xo4.SOUNDS.items():
        assert xo4synth.clean_patch(patch) == dict(xo4synth.PATCH, **patch), name
    assert [k for k, _, _ in xo4.SETTINGS] == list(xo4synth.PATCH)        # every patch setting on the page


def test_drum_levels_ratchets_nudge():
    """a drum hit's level sets its velocity, its ratchet plays it that many times in the step; a step's nudge moves
    it off the grid (64ths of a step); levels and ratchets stay with their pads, cleaned"""
    step = xo4.clean_step({"notes": [5, 1], "levels": [3, 1], "ratchets": [2, 9], "nudge": -50}, xo4.DRUMS)
    assert step["notes"] == [1, 5] and step["levels"] == [1, 3] and step["ratchets"] == [4, 2] and step["nudge"] == -32
    song = song_with(xo4.DRUMS, {0: {"notes": [0], "levels": [3], "ratchets": [2]},
                                 2: {"notes": [4], "levels": [1], "nudge": 16}})
    seq = playing(xo4.Sequencer())
    ons = [(round((t - 10.0) / U, 3), pad, vel) for t, _, kind, pad, vel in seq.due(song, seq.ahead, 10.0, 10.0 + 4 * U)
           if kind == "on"]
    assert ons == [(0.0, 0, 127), (0.5, 0, 127), (2.25, 4, 42)]     # HARD twice; a GHOST a quarter step late


def test_live_rec():
    """REC on and playing: a pad played goes onto the drums' nearest step at the level it was hit; QUANT off keeps
    where it was played; a step not yet sent doesn't play it again; REC off or stopped: nothing recorded"""
    song = xo4.clean_song(None)
    seq = playing(xo4.Sequencer())
    assert not seq.record(song, 2, 100, 10.0 + 4 * U)               # REC off
    seq.rec = True
    seq.due(song, seq.ahead, 10.0, 10.0 + 2 * U)                    # sent up to step 2
    assert seq.record(song, 2, 40, 10.0 + 4 * U + 0.01)             # just after step 4: there, as a GHOST
    step = song["patterns"]["A"][xo4.DRUMS]["steps"][4]
    assert step["notes"] == [2] and step["levels"] == [1] and step["nudge"] == 0
    ons = [pad for t, _, kind, pad, _ in seq.due(song, seq.ahead, 10.0 + 2 * U, 10.0 + 6 * U) if kind == "on"]
    assert ons == []                                                # already heard live: not again this time round
    song["quant"] = False
    assert seq.record(song, 7, 120, 10.0 + 8 * U - U / 4)           # a quarter step early, kept
    step = song["patterns"]["A"][xo4.DRUMS]["steps"][8]
    assert step["notes"] == [7] and step["levels"] == [3] and step["nudge"] == -16
    seq.grid = (PER, None, False)
    assert not seq.record(song, 1, 100, 11.0)                       # stopped
    engine = xo4.Engine(RATE)
    engine.seq.grid, engine.seq.rec = (PER, 10.0, True), True
    assert engine.played(9, 100, 10.0) and engine.song["patterns"]["A"][xo4.DRUMS]["steps"][0]["notes"] == [9]


def test_synth_fx():
    """XO-4's own punch-in FX on its synths: GATE chops a held chord into 16ths, let go it's whole again"""
    import numpy as np
    import padfx
    engine = xo4.Engine(RATE)
    engine.set_song(song_with(xo4.SYNTH1, {0: {"notes": [60, 64, 67], "vel": 127, "len": 16}}))
    engine.seq.grid = (PER, 10.0, True)
    t, blocks = 10.0, []
    for _ in range(int(0.3 * RATE / 512)):                         # into the chord's sustain
        engine.render(512, t)
        t += 512 / RATE
    engine.fx.press(padfx.GATE)
    for _ in range(int(0.5 * RATE / 512)):
        out, _ = engine.render(512, t)
        blocks.append(np.abs(out[:, 0]))
        t += 512 / RATE
    gated = np.concatenate(blocks)[RATE // 20:]
    gated = gated[:len(gated) // 240 * 240]
    quiet = (gated.reshape(-1, 240).max(axis=1) < 0.01).mean()     # 5 ms windows that are silent
    assert 0.2 < quiet < 0.8, quiet                                 # chopped: on and off
    engine.fx.press(None)
    for _ in range(20):
        out, _ = engine.render(512, t)
        t += 512 / RATE
    assert (np.abs(out[:, 0]).reshape(-1, 256).max(axis=1) > 0.01).all()   # whole again


def test_out_level_leaves_room():
    """the channel's sound 6 dB down before it's made 16-bit: full scale comes out at half, twice full scale
    (two loud sounds together) unclipped"""
    import numpy
    block = numpy.array([[1.0, -1.0], [1.98, -1.98]], dtype=numpy.float32)
    out = numpy.frombuffer(xo4.to_pcm(block), dtype="<i2")
    assert list(out) == [16383, -16383, 32439, -32439]


def test_live_keys_on_a_synth():
    """notes from the keys on SYNTH 2: they sound while held; with the sustain pedal down they ring on after
    they're let go, until it's up; all notes off and live_off end them; other tracks' notes are ignored"""
    engine = xo4.Engine(RATE)
    live = xo4.Live(engine.synths)
    s2 = engine.synths[1]
    live.play(xo4.SYNTH2, [[0x90, 60, 100], [0x90, 64, 90]])
    assert s2.sounding() == [60, 64] and engine.synths[0].sounding() == []
    live.play(xo4.SYNTH2, [[0x90, 64, 0]])                     # a note-on at velocity 0: let go
    assert [v.note for v in s2.voices if v.stage not in ("release", "done")] == [60]
    live.play(xo4.SYNTH2, [[0xB0, 64, 127], [0x80, 60, 0]])    # pedal down, then the key up: still held
    assert [v.note for v in s2.voices if v.stage not in ("release", "done")] == [60]
    live.play(xo4.SYNTH2, [[0xB0, 64, 0]])                     # pedal up: let go
    assert [v.note for v in s2.voices if v.stage not in ("release", "done")] == []
    live.play(xo4.SYNTH2, [[0x90, 67, 100], [0xB0, 123, 0]])
    assert [v.note for v in s2.voices if v.stage not in ("release", "done")] == []
    live.play(xo4.SYNTH1, [[0x90, 48, 100]])
    live.play(xo4.DRUMS, [[0x90, 36, 100]])
    assert engine.synths[0].sounding() == [48]
    engine.render(512)                                              # (a block heard before it's let go)
    live.play(xo4.SYNTH1, [[0xE0, 0x7F, 0x7F], [0xB0, 1, 127]])     # the pitch wheel up, the mod wheel up
    assert engine.synths[0].bend > 0.999 and engine.synths[0].wheel == 1.0
    live.play(xo4.SYNTH1, [[0xE0, 0x00, 0x40]])                     # the pitch wheel back to the middle
    assert engine.synths[0].bend == 0.0
    live.play(xo4.SYNTH1, [[0xE0, 0x00, 0x00]])                     # all the way down
    assert engine.synths[0].bend == -1.0 and engine.synths[1].bend == 0.0
    live.off()
    assert engine.synths[0].bend == 0.0 and engine.synths[0].wheel == 0.0     # the wheels let go with the keys
    assert [v for v in engine.synths[0].voices if v.stage not in ("release", "done")] == []
    import numpy as np
    assert np.abs(engine.render(512)[0]).max() > 0                  # the release still heard


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
