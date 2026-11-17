"""The sampler plug-in's 4x4 sampler (plugins/sampler): pads, voices, chokes, envelopes, kits, its PADS tab. No
audio device needed (numpy)."""

import os
import sys
import tempfile
import wave
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="fm1-pads-"))
os.environ.update(FM1_LIBRARY=str(TMP / "library"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fm1-bt-bridge"))

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "sampler"))     # the sampler plug-in's modules (pads, padfx, deskpads)


class Display:
    image = theme = None

    def show_rgb(self, img):
        self.image = img


class FakeProc:
    """the sampler's process, pretend: what's sent to it kept"""
    sounding, step = [], None

    def __init__(self):
        self.sent = []

    def send(self, *msg):
        self.sent.append(msg)


def sampler_app(on=("sampler", "editor")):
    """the Studio with the repository's plug-ins found (as in ~/xoxo-plugins) and some switched on; the sampler's
    process pretend -> (app, its screens, the process)"""
    import copy
    import bridge
    import deskui
    app = bridge.App(Display(), copy.deepcopy(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.plugin_host.dirs = [ROOT / "plugins"]
    app.state["plugins"] = {pid: {"on": True, "settings": {}} for pid in on}
    proc = FakeProc()
    app.plugin_host.processes = {"sampler": proc}
    app.plugin_host.start()
    ui = deskui.DeskUI(app, app.display)
    app.desk = ui
    ui.theme_check = 1e12
    return app, ui, proc


def the_kit(app):
    import padkit
    return padkit.kit(app.plugin_host.loaded["sampler"])


def put_kit(app, kit):
    import padkit
    padkit.set_kit(app.plugin_host.loaded["sampler"], kit)

import numpy as np  # noqa: E402

import pads  # noqa: E402


def wav(name, frames, rate=48000, value=16000):
    path = TMP / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.full(frames, value, dtype="<i2").tobytes())
    return str(path)


def kit(**pads_by_index):
    k = pads.empty_kit()
    for i, settings in pads_by_index.items():
        k["pads"][int(i[1:])].update(settings)
    return k


def test_one_shot_plays_to_its_end():
    e = pads.Engine(48000)
    e.set_kit(kit(p0={"sample": wav("kick.wav", 1000)}))
    e.trigger(0, 127)
    out = e.render(256)
    assert out.shape == (256, 2) and abs(out[100, 0] - 16000 / 32768) < 0.02      # full level, both sides
    assert e.sounding() == [0]
    e.release(0)                                                     # a one-shot ignores the release
    e.render(256)
    assert e.sounding() == [0]
    for _ in range(4):
        e.render(256)
    assert e.sounding() == []                                        # 1000 frames: over


def test_velocity_pan_and_tune():
    e = pads.Engine(48000)
    e.set_kit(kit(p1={"sample": wav("snare.wav", 4800), "pan": 50, "tune": 12}))
    e.trigger(1, 64)
    out = e.render(256)
    assert out[100, 0] == 0 and 0 < out[100, 1] < 16000 / 32768 * 0.5   # panned right, quieter at velocity 64
    frames = 256
    while e.sounding():
        e.render(256)
        frames += 256
    assert frames <= 2600                                            # an octave up: half the length


def test_choke_gate_and_loop():
    e = pads.Engine(48000)
    e.set_kit(kit(p2={"sample": wav("ohat.wav", 48000), "choke": 1},
                  p3={"sample": wav("chat.wav", 2000), "choke": 1},
                  p4={"sample": wav("pad.wav", 48000), "mode": "gate", "release": 10},
                  p5={"sample": wav("loop.wav", 500), "mode": "loop"}))
    e.trigger(2)
    e.render(256)
    e.trigger(3)                                                     # the closed hat cuts the open one
    for _ in range(2):
        e.render(256)
    assert 2 not in e.sounding() and 3 in e.sounding()
    e.trigger(4)
    e.render(256)
    e.release(4)                                                     # a gate pad: stops when let go
    for _ in range(4):
        e.render(256)
    assert 4 not in e.sounding()
    e.trigger(5)
    for _ in range(10):                                              # a 500-frame loop keeps going while held
        e.render(256)
    assert 5 in e.sounding()
    e.midi(bytes([0x80, pads.FIRST_NOTE + 5, 0]))                    # its note let go
    for _ in range(20):
        e.render(256)
    assert 5 not in e.sounding()


def test_midi_notes_and_voices():
    e = pads.Engine(48000)
    e.set_kit(kit(p0={"sample": wav("k.wav", 48000)}))
    e.midi(bytes([0x99, 36, 100]))                                   # C1, any channel: pad 1
    e.midi(bytes([0x90, 35, 100]))                                   # below the pads: nothing
    assert e.sounding() == [0] and len(e.voices) == 1
    for _ in range(pads.VOICES + 5):
        e.trigger(0)
    assert len(e.voices) == pads.VOICES                              # the oldest stopped
    e.set_kit(kit(p1={"sample": wav("cd.wav", 44100, rate=44100)}))  # a 44.1 kHz sample: 48 kHz once, at load
    e.trigger(1)
    assert e.voices[-1]["step"] == 1.0 and abs(len(e.voices[-1]["data"]) - 48000) <= 1
    assert pads.pad_of(51) == 15 and pads.pad_of(52) is None
    pcm = pads.to_pcm(np.array([[2.0, -2.0]], dtype=np.float32))
    assert np.frombuffer(pcm, dtype="<i2").tolist() == [32767, -32767]   # clipped


def test_mpc_layout():
    """the MPC layout, the only one: notes 36-51 on any channel play pads 1-16"""
    assert pads.MAPS == ("mpc",)
    assert pads.pad_of(36, 9) == 0 and pads.pad_of(38, 0) == 2 and pads.pad_of(51, 15) == 15
    assert pads.pad_of(35) is None and pads.pad_of(52, 9) is None
    assert pads.note_of(0) == 36 and pads.note_of(15) == 51
    e = pads.Engine(48000)
    e.set_kit(kit(p2={"sample": wav("sn.wav", 48000)}))
    e.midi(bytes([0x93, 38, 100]))                                   # channel 4: pad 3 all the same
    assert e.sounding() == [2]
    assert pads.clean_kit({"map": "weird"})["map"] == "mpc" and pads.clean_kit({"map": "sloop"})["map"] == "mpc"


def test_sequencer_timing():
    """SLOOP's drum sequencer: steps on the beat grid, odd steps swung late, ratchets share their step, a nudge
    moves the whole step, the pattern loops at LEN, nothing before PLAY or after STOP"""
    seq = pads.empty_seq()
    seq["len"], seq["swing"] = 4, 50
    seq["steps"][0] = [[0, 0, 1]]
    seq["steps"][1] = [[1, 3, 1]]                                    # HARD
    seq["steps"][2] = [[2, 1, 2]]                                    # GHOST, ratchet x2
    seq["steps"][3] = [[3, 0, 1]]
    seq["micro"][3] = 16                                             # a quarter step late
    sq = pads.Sequencer()
    assert sq.events(seq, 0.0, 1.0) == []                            # no grid: nothing
    per = 60 / (120 * 24)                                            # 120 BPM: a 16th is 0.125 s
    sq.grid = (per, 10.0, True)
    ons = [e for e in sq.events(seq, 10.0, 10.5) if e[1] == "on"]
    sw = 50 * 0.125 / 200                                            # swing 50: odd steps a quarter step late
    want = [(10.0, 0, 100), (10.125 + sw, 1, 127), (10.25, 2, 42), (10.25 + (0.125 + sw) / 2, 2, 42),
            (10.375 + sw + 16 * 0.125 / 64, 3, 100)]
    assert [(round(t, 6), p, v) for t, _, p, v in ons] == [(round(t, 6), p, v) for t, p, v in want]
    assert sq.step == 3
    later = [e for e in sq.events(seq, 10.5, 10.6) if e[1] == "on"]
    assert later and later[0][2] == 0 and abs(later[0][0] - 10.5) < 1e-9   # step 0 again: LEN 4 loops
    sq.grid = (per, None, False)                                     # STOP
    sq.events(seq, 10.6, 10.7)
    assert sq.step is None and sq.pending == []
    seq["div"] = 4                                                   # 8T: three a beat, never swung
    sq.grid = (per, 20.0, True)
    times = [round(t - 20, 6) for t, kind, _, _ in sq.events(seq, 20.0, 20.4) if kind == "on"]
    assert times[:2] == [0.0, round(0.5 / 3, 6)]


def test_sequencer_in_the_engine():
    """a hit starts at its own frame inside a block; live REC puts a played pad on the nearest step (QUANT
    off: with its nudge) and doesn't play it twice"""
    e = pads.Engine(48000)
    k = kit(p0={"sample": wav("seqk.wav", 48000)})
    k["seq"]["steps"][1] = [[0, 0, 1]]
    e.set_kit(k)
    per = 60 / (120 * 24)
    e.seq.grid = (per, 0.0, True)
    out = e.render(512, 0.125 - 100 / 48000)                         # step 1 is due 100 frames into this block
    assert abs(out[99, 0]) < 1e-6 and abs(out[101, 0]) > 0.01
    e.seq.rec = True
    k = e.kit
    assert e.hit(5, 100, now=0.25 + 0.006)                           # just after step 2
    assert [5, 0, 1] in e.kit["seq"]["steps"][2] and e.kit["seq"]["micro"][2] == 0
    assert (2, 5) in e.seq.skip                                      # heard as played: not again on step 2
    e.kit["seq"]["quant"] = False
    e.hit(6, 50, now=0.375 - 0.01)                                   # a little early for step 3, softly: GHOST
    assert [6, 1, 1] in e.kit["seq"]["steps"][3] and e.kit["seq"]["micro"][3] == -5
    e.seq.rec = False
    assert not e.hit(7, 100, now=0.5)


def test_note_repeat():
    """note repeat: a held pad plays again at the repeat's division, on the grid while the sequencer plays,
    from the press while stopped; let go, it stops; recorded with live REC"""
    e = pads.Engine(48000)
    e.set_kit(kit(p0={"sample": wav("rep.wav", 4800)}))
    per = 60 / (120 * 24)
    e.seq.grid = (per, None, False)                                  # stopped, 120 BPM
    e.seq.repeat = 2                                                 # 1/16: every 0.125 s
    e.hit(0, 90, now=5.0)
    ons = [ev for ev in e.seq.events(e.kit["seq"], 5.0, 5.4) if ev[1] == "on"]
    assert [round(t, 6) for t, _, _, _ in ons] == [5.125, 5.25, 5.375] and ons[0][3] == 90
    e.seq.let_go(0)
    assert e.seq.events(e.kit["seq"], 5.4, 6.0) == []
    e.seq.grid, e.seq.rec, e.seq.repeat = (per, 10.0, True), True, 1    # playing from 10.0, 1/8
    e.hit(1, 100, now=10.26)                                          # held from just after beat 1's 8th
    ons = [ev for ev in e.seq.events(e.kit["seq"], 10.26, 10.8) if ev[1] == "on" and ev[2] == 1]
    assert [round(t, 6) for t, _, _, _ in ons] == [10.5, 10.75]       # on the 8ths of the grid
    steps = e.kit["seq"]["steps"]
    assert [1, 0, 1] in steps[2] and [1, 0, 1] in steps[4] and [1, 0, 1] in steps[6] and e.seq.dirty
    e.seq.repeat = None
    assert not [ev for ev in e.seq.events(e.kit["seq"], 10.8, 11.0) if ev[2] == 1]


def test_the_editor_and_the_pads():
    """the sample editor plug-in: EDITOR opens it (its OPEN list the first time, then the file last edited), OPEN
    lists the samples and takes, BACK goes list > take > HOME; with the sampler plug-in on, TO PAD saves the edit
    onto a pad and opens its page in PADS, and a pad's TRIM opens its sample, BACK going to the pad's page"""
    import time as clock
    import deskui
    import library
    t = np.arange(24000) / 48000
    with wave.open(str(library.folder("samples") / "tone.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes((np.sin(2 * np.pi * 220 * t) * 12000).astype("<i2").tobytes())
    app, ui, proc = sampler_app()
    assert "SAMPLE EDITOR" not in [m[0] for m in deskui.MORE]
    screen = ui.editor_screen()[1]

    def touch(key):
        ui.render(0.0, force=True)
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        ui.touch("up", box[0] + 4, box[1] + 4, 0.0)
        ui.render(0.0, force=True)

    def opened():
        for _ in range(200):
            if not app.ed["loading"]:
                return
            clock.sleep(0.02)
    ui.open_tab("EDITOR")                                            # EDITOR, the first time: its OPEN list
    assert ui.tab == "EDITOR" and app.screen == "editor" and app.ed is None and screen.ed_files
    touch(("browse", "samples"))
    touch(("file", "tone.wav"))
    opened()
    assert app.screen == "editor" and app.ed["name"] == "tone.wav" and not screen.ed_files
    touch("ed-open")                                                 # OPEN again: the list over the take
    assert screen.ed_files
    touch("ed-back")                                                 # BACK: to the take
    assert not screen.ed_files and app.ed["name"] == "tone.wav"
    touch("ed-back")                                                 # BACK again: out of the editor
    assert app.screen == "status" and ui.tab == "HOME"
    ui.open_tab("EDITOR")                                            # EDITOR again: the file last edited
    opened()
    assert app.ed["name"] == "tone.wav" and not screen.ed_files
    touch("ed-to-pad")
    touch(("ed-pad", 7))
    pad = the_kit(app)["pads"][7]
    assert pad["sample"] and Path(pad["sample"]).exists() and Path(pad["sample"]).name != "tone.wav"
    pads_tab = ui.plugin_tab("PADS")
    assert app.screen == "status" and ui.tab == "PADS" and pads_tab.pad_edit == 7
    assert any(w[3] == "pad-back" for w in ui.widgets)               # the pad's page
    k = the_kit(app)                                                 # a pad's TRIM: its sample in the editor
    k["pads"][7]["sample"] = str(library.folder("samples") / "tone.wav")
    put_kit(app, k)
    touch(("pad-act", "TRIM"))
    opened()
    assert app.screen == "editor" and app.ed["name"] == "tone.wav" and pads_tab.pad_trim == 7
    ui.render(0.0, force=True)
    assert any(w[3] == "ed-save" for w in ui.widgets)
    touch("ed-back")                                                 # BACK: the pad's page again
    assert app.screen == "status" and ui.tab == "PADS" and pads_tab.pad_edit == 7 and pads_tab.pad_trim is None


def test_the_editor_without_the_sampler():
    """the editor on, the sampler off: no TO PAD; the editor works on its own"""
    app, ui, proc = sampler_app(on=("editor",))
    ui.open_tab("EDITOR")
    ui.render(0.0, force=True)
    assert ui.plugin_tab("PADS") is None and "PADS" not in ui.tabs()
    assert not any(w[3] == "ed-to-pad" for w in ui.widgets)


def test_kits():
    k = pads.clean_kit({"name": "BOOM BAP", "pads": [{"sample": "x.wav", "level": 999, "mode": "weird"}]})
    assert len(k["pads"]) == 16 and k["pads"][0]["level"] == 200 and k["pads"][0]["mode"] == "one-shot"
    path = pads.save_kit(k)
    assert path.name == "BOOM-BAP.json" and "BOOM-BAP" in pads.list_kits()
    assert pads.load_kit(path)["pads"][0]["sample"] == "x.wav"


def test_factory_kits():
    """the ready-made 808 KIT: made once into the library, its sounds in the samples folder (listed after the
    user's own), each one playable; deleted, it isn't made again; a sample of the same name the user has already is
    left alone"""
    import library
    samples = library.folder("samples")
    mine = samples / "808-COWBELL.wav"
    mine.write_bytes(b"mine")
    pads._factory_checked = False
    assert "808-KIT" in pads.list_kits()
    assert mine.read_bytes() == b"mine" and (samples / "808-KICK.wav").stat().st_mtime < 1e9
    eight = pads.load_kit(pads.kit_path("808 KIT"))
    assert eight["map"] == "mpc" and Path(eight["pads"][0]["sample"]).name == "808-KICK.wav"
    assert [p["choke"] for p in eight["pads"][4:7]] == [1, 1, 1] and eight["pads"][2]["choke"] == 0
    mine.unlink()
    e = pads.Engine()
    for pad in eight["pads"][:15]:
        assert e.sample(pad["sample"]) is not None, pad["sample"]           # 16-bit WAVs the engine loads
    pads.kit_path("808 KIT").unlink()
    pads._factory_checked = False
    assert "808-KIT" not in pads.list_kits()                                 # deleted: stays deleted


def test_first_kit_is_the_808():
    """a first start (no kit chosen yet): the pads have the 808 KIT, so they play out of the box; a kit chosen later
    stays"""
    import library
    was = library.LIBRARY
    library.LIBRARY, pads._factory_checked = TMP / "fresh-library", False
    try:
        app, ui, proc = sampler_app()
        kit = the_kit(app)
        assert kit["name"] == "808 KIT" and Path(kit["pads"][0]["sample"]).name == "808-KICK.wav"
        assert app.state["plugins"]["sampler"]["settings"]["kit"]["name"] == "808 KIT"   # kept: made once
        put_kit(app, pads.empty_kit("MINE"))
        assert the_kit(app)["name"] == "MINE" and proc.sent[-1][0] == "kit"
    finally:
        library.LIBRARY, pads._factory_checked = was, False


def test_pads_tab():
    """the sampler plug-in's PADS tab: a pad sounds while held (until let go), RPT steps the note repeat, MIDI IN
    switches the routes' notes on the pads, EDIT and a pad open its page, - / + and choices change it, a sample
    picked goes on it, kits save, load and start afresh"""
    import library
    app, ui, proc = sampler_app()
    assert ui.tabs() == ("HOME", "MIX", "MIDI", "REC", "SEQ", "PADS", "EDITOR", "MORE")
    ui.open_tab("PADS")
    tab = ui.plugin_tab("PADS")
    ui.render(0.0, force=True)

    def touch(key, hold=False):
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        if not hold:
            ui.touch("up", box[0] + 4, box[1] + 4, 0.0)
        ui.render(0.0, force=True)
    k = the_kit(app)
    k["pads"][0]["sample"] = wav("hit.wav", 1000)
    put_kit(app, k)
    ui.render(0.0, force=True)
    touch(("pad", 0), hold=True)                                     # held: sounding, not yet let go
    assert proc.sent[-1] == ("tap", 0, 110)
    ui.touch("up", 0, 0, 0.0)
    assert proc.sent[-1] == ("untap", 0)
    touch("pad-repeat")
    touch("pad-repeat")
    settings = app.state["plugins"]["sampler"]["settings"]
    assert settings["repeat"] == 2 and proc.sent[-1] == ("repeat", 2)      # RPT 1/16
    touch("pads-midi-in")
    assert settings["midi_in"] is True and proc.sent[-1] == ("midi_in", True)
    touch("pad-mode")                                                # EDIT, then pad 5
    assert tab.pad_mode
    touch(("pad", 4))
    assert tab.pad_edit == 4 and ui.tab == "PADS"
    touch(("pad+", "level"))
    touch(("pad-", "tune"))
    touch("pad-down")                                                # MODE is further down the page
    touch(("pad-row", "mode"))
    touch("pad-up")
    pad = the_kit(app)["pads"][4]
    assert (pad["level"], pad["tune"], pad["mode"]) == (105, -1, "gate")
    wav("snare.wav", 1000)
    sample = library.folder("samples") / "snare.wav"
    sample.write_bytes((TMP / "snare.wav").read_bytes())
    touch(("pad-row", "sample"))                                     # the samples folder, as a Studio page
    assert app.screen == "pick"
    app.pick["on"]("snare.wav")
    ui.render(0.0, force=True)
    assert the_kit(app)["pads"][4]["sample"] == str(sample) and app.screen == "status"
    assert proc.sent[-1][0] == "kit"                                 # the engine has the kit
    touch("pad-back")                                                # BACK: the pads again
    assert tab.pad_edit is None and ui.tab == "PADS"
    touch("kits")                                                    # the kit's name: KITS
    assert tab.kits_open
    touch("kit-save")
    assert "KIT-1" in pads.list_kits()
    touch("kit-new")
    assert the_kit(app)["name"] == "KIT 2" and not the_kit(app)["pads"][4]["sample"]
    touch("kits")
    touch(("kit", "KIT-1"))
    assert the_kit(app)["pads"][4]["sample"] == str(sample)          # loaded back
    if tab.kits_open:
        touch("kits-back")
    touch("pads-home")
    assert ui.tab == "HOME"


def test_the_sampler_off():
    """the sampler plug-in off: no PADS tab, no PADS in the mixer, no kits on the web page"""
    import bridge
    app, ui, proc = sampler_app(on=())
    assert "PADS" not in ui.tabs() and ui.plugin_tab("PADS") is None
    ui.open_tab("PADS")
    assert ui.tab == "HOME"
    node = {"type": "PipeWire:Interface:Node", "id": 70,
            "info": {"props": {"media.class": "Audio/Source", "node.name": "fm1-xo4"}}}
    assert bridge.pick_nodes([node], app.plugin_host)[1] == []
    st = app.web_status()
    assert st["kits"] is None and st["plugins"]["builtin"]["sampler"] is False


def test_sampler_in_the_box():
    """the sampler's notes from the MIDI routes (SMP: all of them to its process, its MIDI IN decides), and its
    sound a source in the mixer"""
    import blemidi
    import bridge

    class Conn:
        def __init__(self):
            self.sent = []

        def send(self, msg):
            self.sent.append(msg)
    b = blemidi.MidiBridge(pads=Conn())
    b.to_ble = lambda m: None
    b.controllers.send_messages = lambda messages: None
    b.from_controllers(bytes([0x99, 36, 100]))                       # USB keys > SMP: on at first
    assert b.pads.sent == [("midi", [[0x99, 36, 100]])]
    assert blemidi.default_routes()["Box>SMP"]["on"] is False
    node = {"type": "PipeWire:Interface:Node", "id": 70,
            "info": {"props": {"media.class": "Audio/Source", "node.name": "fm1-xo4"}}}   # (the pads' channel)
    port = {"type": "PipeWire:Interface:Port", "id": 71,
            "info": {"props": {"node.id": 70, "port.name": "capture_FL", "port.direction": "out", "port.id": 0}}}
    app, ui, proc = sampler_app(on=("sampler",))
    _, others = bridge.pick_nodes([node, port], app.plugin_host)   # (the sampler on: its PADS)
    assert others[0]["label"] == "PADS" and bridge.device_keys(others) == ["u-xo4"]   # (its level's key as it was)



def test_out_level_leaves_room():
    """the channel's sound 6 dB down before it's made 16-bit: full scale comes out at half, twice full scale
    (two loud sounds together) unclipped"""
    import numpy
    block = numpy.array([[1.0, -1.0], [1.98, -1.98]], dtype=numpy.float32)
    out = numpy.frombuffer(pads.to_pcm(block), dtype="<i2")
    assert list(out) == [16383, -16383, 32439, -32439]


if __name__ == "__main__":
    tests = [(n, f) for n, f in globals().items() if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"all {len(tests)} passed")
