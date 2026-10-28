"""The desk box (Pi 3/4 + 3.5" touchscreen): which build a box is, the touch buttons, the screen writes.
No touchscreen needed (needs Pillow and numpy)."""

import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fm1-bt-bridge"))

from PIL import Image, ImageDraw  # noqa: E402

import desk  # noqa: E402
import device  # noqa: E402

PI3 = "Raspberry Pi 3 Model B Plus Rev 1.3"
ZERO = "Raspberry Pi Zero W Rev 1.1"
TFT = ("/dev/fb1", 480, 320)


def test_which_box():
    assert device.detect(model=ZERO, screen=None)["build"] == "pocket"
    pocket = device.detect(model=ZERO, screen=TFT)                    # a Zero is the pocket box, screen or not
    assert pocket["build"] == "pocket" and "usb_ports" not in pocket["can"] and "touch" not in pocket["can"]
    box = device.detect(model=PI3, screen=TFT)
    assert box["build"] == "desk" and {"touch", "color", "usb_ports"} <= box["can"]
    assert device.detect(model=PI3, screen=None)["build"] == "pocket"   # no touchscreen yet: the OLED's code
    assert device.detect("desk", model=ZERO, screen=None)["build"] == "desk"     # the setting wins
    with tempfile.TemporaryDirectory() as tmp:                       # the framebuffer's size from sysfs
        root = Path(tmp)
        (root / "fb0").mkdir()
        (root / "fb0" / "virtual_size").write_text("1920,1080\n")    # HDMI: not the touchscreen
        assert device.touchscreen(root) is None
        (root / "fb1").mkdir()
        (root / "fb1" / "virtual_size").write_text("480,320\n")
        assert device.touchscreen(root) == ("/dev/fb1", 480, 320)
    with tempfile.TemporaryDirectory() as tmp:                       # the DRM driver, no HDMI at boot: fb0
        root = Path(tmp)
        (root / "fb0").mkdir()
        (root / "fb0" / "virtual_size").write_text("480,320\n")
        (root / "fb0" / "name").write_text("ili9486drmfb\n")
        assert device.touchscreen(root) == ("/dev/fb0", 480, 320)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        model = root / "model"
        model.write_bytes(PI3.encode() + b"\0")
        assert device.board(model) == PI3


def test_buttons_and_touch_mapping():
    assert desk.button_at(80, 230) == "key1" and desk.button_at(240, 290) == "press"
    assert desk.button_at(240, 100) is None                           # the picture: no button
    cal = [3900, 200, 3900, 200, True]                                # chip x up the screen, both reversed
    assert desk.to_screen(3900, 3900, cal) == (0, 0)
    assert desk.to_screen(200, 200, cal) == (479, 319)
    assert desk.to_screen(9999, -50, cal) == (479, 0)                 # out of range: clamped
    assert desk.to_screen(3900, 3900, [0, 4000, 0, 4000, False]) == (467, 311)


class FakeTimer:
    def __init__(self):
        self.log = []

    def pressed(self, name, now):
        self.log.append(("down", name))

    def released(self, name, now):
        self.log.append(("up", name))


class FakeDisplay:
    def __init__(self):
        self.lit = []

    def press(self, name):
        self.lit.append(name)


def test_touch_presses_buttons():
    timer, display = FakeTimer(), FakeDisplay()
    cal = [0, 479, 0, 319, False]                                     # raw = screen, for the test
    t = desk.Touch(timer, display, cal)

    def touch(x, y, down=True):
        t.event(desk.EV_ABS, desk.ABS_X, x, 0)
        t.event(desk.EV_ABS, desk.ABS_Y, y, 0)
        t.event(desk.EV_KEY, desk.BTN_TOUCH, int(down), 0)
        t.event(desk.EV_SYN, 0, 0, 0)
    touch(240, 290)                                                   # on ●
    touch(242, 292)                                                   # the finger wobbles: still held
    touch(330, 290)                                                   # slides onto ▼
    touch(330, 290, down=False)
    assert timer.log == [("down", "press"), ("up", "press"), ("down", "down"), ("up", "down")]
    assert display.lit == ["press", "down", None]


def test_touch_calibration():
    """four targets tapped -> touch_cal that puts a finger where it is, whichever way the chip is turned; taps
    that don't line up start it again"""
    import bridge
    import deskui
    for real in ([3900, 200, 3800, 300, True], [150, 3950, 250, 3850, False]):
        def raw_of(x, y):                                            # the chip's reading at screen point (x, y)
            rx = real[0] + x * (real[1] - real[0]) / (desk.W - 1)
            ry = real[2] + y * (real[3] - real[2]) / (desk.H - 1)
            return (round(ry), round(rx)) if real[4] else (round(rx), round(ry))
        i = desk.CAL_INSET
        targets = [(i, i), (desk.W - 1 - i, i), (i, desk.H - 1 - i), (desk.W - 1 - i, desk.H - 1 - i)]
        cal = desk.calibration([raw_of(*p) for p in targets])
        assert cal[4] == real[4] and all(abs(a - b) <= 2 for a, b in zip(cal[:4], real[:4]))
        assert desk.to_screen(*raw_of(100, 200), cal) == (100, 200)
    assert desk.calibration([(2000, 2000)] * 4) is None
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, touch_cal=list(bridge.DEFAULTS["touch_cal"])))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    t = desk.Touch(FakeTimer(), FakeDisplay(), app.state["touch_cal"], ui=ui,
                   ui_touch=lambda kind, x, y: ui.touch(kind, x, y, 0.0))
    ui.calibrate()
    ui.render(0.0, force=True)
    assert not ui.widgets                                            # nothing to tap by mistake

    def finger(rx, ry):
        for down in (True, False):
            t.event(desk.EV_ABS, desk.ABS_X, rx, 0)
            t.event(desk.EV_ABS, desk.ABS_Y, ry, 0)
            t.event(desk.EV_KEY, desk.BTN_TOUCH, int(down), 0)
            t.event(desk.EV_SYN, 0, 0, 0)
    for _ in range(4):
        finger(2000, 2000)                                           # the same spot four times: again
    assert ui.cal == [] and "again" in app.message
    for raw in ((3700, 3800), (3700, 300), (350, 3800), (350, 300)):
        finger(*raw)
    assert ui.cal is None and app.state["touch_cal"] == t.cal and t.cal != bridge.DEFAULTS["touch_cal"]
    assert desk.to_screen(3700, 3800, t.cal) == (desk.CAL_INSET, desk.CAL_INSET)


def test_headphone_jack():
    """the Studio's 3.5 mm jack: found in PipeWire, the sound to the speaker, the jack or both, the click and
    previews to the jack only with cue on, its own level"""
    import bridge
    sink = {"id": 5, "name": "bluez_output.AA", "label": "Speaker"}
    objects = [{"type": "PipeWire:Interface:Node", "id": 9, "info": {"props": {
        "media.class": "Audio/Sink", "node.name": "alsa_output.platform-bcm2835_audio.stereo-fallback",
        "node.description": "Built-in Audio Stereo", "alsa.card_name": "bcm2835 Headphones"}}},
        {"type": "PipeWire:Interface:Node", "id": 10, "info": {"props": {
            "media.class": "Audio/Sink", "node.name": "alsa_output.platform-fef00700.hdmi.hdmi-stereo",
            "alsa.card_name": "vc4-hdmi"}}}]
    jack = bridge.jack_node(objects)
    assert jack["id"] == 9 and bridge.jack_node(objects[1:]) is None
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.sink, app.jack = sink, jack
    assert app.outputs() == (sink["name"], jack["name"])            # both: the speaker, and a copy on the jack
    app.state["output"] = "phones"
    assert app.outputs() == (jack["name"], None)
    app.state["output"] = "speaker"
    assert app.outputs() == (sink["name"], None) and app.cue_target() == sink["name"]
    app.state["cue"] = True
    assert app.cue_target() == jack["name"]                          # the click: the jack only
    app.sink = None
    assert app.outputs() == (jack["name"], None)                     # no speaker: the jack
    app.settings_menu = "audio"
    keys = [r[0] for r in app.settings_rows()]
    assert "output" in keys and "cue" in keys
    app.setting = keys.index("output")
    app.change_setting()
    assert app.state["output"] == "phones"
    app.jack = None
    assert "output" not in [r[0] for r in app.settings_rows()]      # the Pocket: no jack, no rows
    app.set_phones(150)
    assert app.state["phones"] == 100


def test_cue_sources():
    """a DJ mixer's cue: a source tapped CUE on the MIX tab plays on the jack before its fader, its own loopback;
    the blend of cue and main mix; the main mix copied to the jack even with output "speaker" while cueing"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, cues=[]))
    app.save_settings = lambda: None
    app.sink = {"id": 5, "name": "bluez_output.AA", "label": "Speaker"}
    app.jack = {"id": 9, "name": "alsa_output.bcm2835", "label": "PHONES"}
    app.others = [{"id": 1, "name": "alsa_input.usb-ep136", "label": "EP-136", "ports": []},
                  {"id": 3, "name": "alsa_input.usb-smk37", "label": "SMK-37+VA", "ports": []}]
    app.state["output"] = "speaker"
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIX")
    ui.render(0.0, force=True)
    assert app.outputs() == ("bluez_output.AA", None) and app.cue_levels() == (100, 100)

    def tap(key):
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        ui.touch("up", box[0] + 4, box[1] + 4, 0.0)
        ui.render(0.0, force=True)
    tap(("cue", "u-smk37va"))
    assert app.cued() == ["u-smk37va"] and app.outputs() == ("bluez_output.AA", "alsa_output.bcm2835")
    started = []
    app.cue_mixer.channels = {}
    ensure, bridge.Loopback.ensure = bridge.Loopback.ensure, (lambda self, source, sink, name=None, pair=None:
                                                              started.append((source, sink, name)))
    try:
        app.cue_mixer.ensure(app.jack["name"], [("u-smk37va", "alsa_input.usb-smk37", None)])
    finally:
        bridge.Loopback.ensure = ensure
    assert started == [("alsa_input.usb-smk37", "alsa_output.bcm2835", "fm1-cue-u-smk37va")]
    tap("cue-mix")                                                   # 50/50 -> 25/75: more of the main mix
    assert app.state["cue_mix"] == 75 and app.cue_levels() == (50, 100)
    for _ in range(2):
        tap("cue-mix")
    assert app.state["cue_mix"] == 0 and app.cue_levels() == (100, 0)   # the cued source only
    tap(("cue", "u-smk37va"))
    assert app.cued() == [] and app.cue_levels() == (100, 100)
    app.state["cues"] = ["u-smk37va"]
    app.jack = None
    assert app.cued() == []                                          # no jack: no cue


def test_decks_screen():
    """the DECKS tab: the decks' screen from their status; its buttons send the decks their commands (a pretend
    decks program: no sound, no Hercules)"""
    import bridge
    import deskui
    sent = []

    class Decks:
        library = [["a.mp3", "Curtains", "7 Keys", 140.0, "E", "12B"],
                   ["b.mp3", "Organ Donor", "Zomboy", 140.0, "F#m", "11A"]]
        overviews, note = {0: [0.5] * 220, 1: []}, None
        library_n = note_n = 0

        def start(self):
            pass

        def stop(self):
            pass
        status = {"decks": [{"title": "Curtains", "artist": "7 Keys", "bpm": 140.0, "key": "E", "camelot": "12B",
                             "pos": 10.0, "len": 240.0, "playing": True, "pitch": 0.0, "cues": [0.1]}, {}],
                  "xfade": 0.5, "cursor": 0, "scanning": None}

        def running(self):
            return True

        def send(self, *cmd):
            sent.append(cmd)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.decks_proc, ui.tab = Decks(), "DECKS"
    ui.render(0.0, force=True)
    keys = {w[3]: w for w in ui.widgets}
    assert ("tab", "HOME") not in keys                     # full screen: no tab bar

    def tap(key):
        box = keys[key][0]
        ui.touch("down", box[0] + 2, box[1] + 2, 0.0)
        ui.touch("up", box[0] + 2, box[1] + 2, 0.1)
    tap(("deck", "PLAY", 0))
    tap(("deck-row", 1))
    tap("decks-load-b")
    box = keys[("deck-cue", 1)][0]
    ui.touch("down", box[0] + 2, box[1] + 2, 0.0)
    ui.touch("up", box[0] + 2, box[1] + 2, 0.2)
    box = keys[("deck-seek", 0)][0]                        # dragged along: the deck goes where the finger is
    ui.touch("down", box[0] + 20, box[1] + 6, 0.0)
    ui.touch("move", (box[0] + box[2]) // 2, box[1] + 6, 0.05)
    ui.touch("up", (box[0] + box[2]) // 2, box[1] + 6, 0.1)
    assert sent[:5] == [("play", 0), ("select", 1), ("load", 1), ("cue", 1, True), ("cue", 1, False)]
    assert sent[5][:2] == ("seek", 0) and 0.45 < sent[5][2] < 0.55 and len(sent) == 6
    assert ui.decks_full is None
    ui.touch("down", box[0] + 40, box[1] + 6, 0.0)          # tapped (a resistive screen's wobble): full screen
    ui.touch("move", box[0] + 42, box[1] + 7, 0.05)
    ui.touch("up", box[0] + 42, box[1] + 7, 0.1)
    assert ui.decks_full == 0 and len(sent) == 6
    ui.render(1.0, force=True)
    keys = {w[3]: w for w in ui.widgets}
    assert list(keys) == ["decks-full"]                     # nothing else on it: any tap goes back
    tap("decks-full")
    assert ui.decks_full is None
    ui.decks_full = 0                                       # left full screen: the decks open on their screen
    ui.open_decks()
    assert ui.decks_full is None and ui.tab == "DECKS"
    said, say_was = [], ui.app.say
    ui.app.say = lambda text, seconds=3: said.append(text)
    for n in (1, 1, 2):                                     # a note popped up once, the same note again too
        ui.decks_proc.note, ui.decks_proc.note_n = "USB drive Zine: 37 tracks", n
        ui.render(1.5 + n, force=True)
    ui.app.say = say_was
    assert said == ["USB drive Zine: 37 tracks"] * 2
    ui.render(2.0, force=True)
    keys = {w[3]: w for w in ui.widgets}
    tap("decks-home")
    assert ui.tab == "HOME"


def test_decks_learn_screens():
    """DECKS > LEARN: the controllers plugged in, one picked; a control to learn (BACK / SKIP / DONE); a map's
    list (a row tapped: that one learnt again; LEARN ALL; held: forgotten), from a pretend decks program"""
    import bridge
    import deskui
    import decks
    sent = []

    class Decks:
        library, overviews, note = [], {0: [], 1: []}, None
        library_n = note_n = 0
        status = {"decks": [{}, {}], "xfade": 0.5, "cursor": 0, "scanning": None,
                  "ports": [["DJControl Inpulse 200 MK2:DJControl Inpulse 200 MK2 MIDI 1", False, True],
                            ["K.O. Sidekick:K.O. Sidekick MIDI 1", False, False]], "learn": None}

        def start(self):
            pass

        def stop(self):
            pass

        def running(self):
            return True

        def send(self, *cmd):
            sent.append(cmd)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.decks_proc, ui.tab = Decks(), "DECKS"
    now = [0.0]

    def tap(key, hold=0.1):
        ui.render(now[0], force=True)
        box = {w[3]: w for w in ui.widgets}[key][0]
        ui.touch("down", box[0] + 2, box[1] + 2, now[0])
        if hold > 0.5:                                              # held: it goes while the finger's still down
            ui.render(now[0] + hold)
        ui.touch("up", box[0] + 2, box[1] + 2, now[0] + hold)
        now[0] += 1 + hold
    tap("decks-learn")
    assert ui.decks_learn
    tap(("learn-port", "K.O. Sidekick:K.O. Sidekick MIDI 1"))       # no map: learning starts
    tap(("learn-port", "DJControl Inpulse 200 MK2:DJControl Inpulse 200 MK2 MIDI 1"))   # built in: its list
    assert sent == [("learn", "K.O. Sidekick:K.O. Sidekick MIDI 1", True),
                    ("learn_list", "DJControl Inpulse 200 MK2:DJControl Inpulse 200 MK2 MIDI 1")]
    L = decks.Learner("K.O. Sidekick:K.O. Sidekick MIDI 1", [], True, 2)   # what the decks would say: A's SHIFT
    Decks.status["learn"] = L.status()
    for key in ("learn-prev", "learn-skip", "learn-done", "learn-back"):
        tap(key)
    assert sent[2:] == [("learn_back",), ("learn_skip",), ("learn_done",), ("learn_done",)]
    del sent[:]
    L.step = len(decks.LEARN)                                       # the list
    L.binds = [{"action": "a.play", "type": "note", "ch": 1, "num": 7}]
    D = decks.Decks.__new__(decks.Decks)
    D.learner = L
    Decks.status["learn"] = D.learn_status()
    ui.render(now[0], force=True)
    rows = [w[3] for w in ui.widgets if isinstance(w[3], tuple) and w[3][0] == "learn-row"]
    assert len(rows) == 9
    tap(("learn-row", 3))                                           # the 4th control: A's PLAY
    tap("learn-down")
    assert ui.decks_learn_top == 9
    tap("learn-all")
    tap("learn-forget", hold=deskui.HOLD + 0.1)
    tap("learn-back")
    port = "K.O. Sidekick:K.O. Sidekick MIDI 1"
    assert sent == [("learn", port, False, "a.play"), ("learn", port, True), ("learn_forget",), ("learn_end",)]


def test_decks_in_the_mixer():
    """the DJ decks while they run: a DECKS channel in MIXER (its level, CUE on the jack); Settings > Audio > DJ
    decks out (STUDIO / HERCULES) told to the decks; with an app or the decks playing, recordings take the speaker"""
    import bridge
    import deskui
    sent = []

    class Decks:
        library, overviews, note, status = [], {0: [], 1: []}, None, None
        library_n = note_n = 0

        def start(self):
            pass

        def running(self):
            return True

        def send(self, *cmd):
            sent.append(cmd)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.jack = {"id": 9, "name": "alsa_output.bcm2835", "label": "PHONES"}
    ui = deskui.DeskUI(app, app.display)
    app.desk = ui
    ui.theme_check = 1e12
    ui.render(0.0, force=True)
    ui.open_tab("MIX")
    ui.render(0.0, force=True)
    assert not any(w[3] == ("slide", "decks") for w in ui.widgets)   # not running: no channel
    ui.decks_proc = Decks()
    ui.open_decks()
    assert sent[-1] == ("output", "studio")
    ui.open_tab("MIX")
    ui.render(1.0, force=True)
    keys = {w[3]: w for w in ui.widgets}
    assert ("slide", "decks") in keys and ("cue", "decks") in keys
    keys[("cue", "decks")][2]()
    assert "decks" in app.state["cues"]
    app.screen, app.settings_menu = "settings", "audio"
    row = next(i for i, r in enumerate(app.settings_rows()) if r[0] == "decks_out")
    assert app.settings_rows()[row][2] == "studio"
    app.setting = row
    app.change_setting()
    assert app.state["decks_out"] == "hercules" and sent[-1] == ("output", "hercules")
    app.screen = "status"
    app.sink, app.others = {"id": 2, "name": "bluez_output.jbl", "label": "JBL"}, [{"id": 1, "name": "usb-in"}]
    assert app.capture_target() == "monitor:bluez_output.jbl"       # one source: what the speaker plays
    app.app_here = {"decks"}
    assert app.capture_target() == "monitor:bluez_output.jbl"       # the decks playing too: the same
    app.sink = app.jack = app.card = None
    assert app.capture_target() == "usb-in"                         # nothing to play on: the source itself


def test_hdmi_mirror():
    """a monitor on HDMI: the KMS framebuffer found (not the touchscreen's), the screen scaled up by a whole
    number and centred, in its pixel format; nothing while unplugged"""
    import numpy as np
    root = Path(tempfile.mkdtemp(prefix="fm1-fb-"))
    for name, fbname, size, bpp in (("fb0", "vc4drmfb", "1280,720", 32), ("fb1", "fb_ili9486", "480,320", 16)):
        (root / name).mkdir()
        (root / name / "name").write_text(fbname + "\n")
        (root / name / "virtual_size").write_text(size + "\n")
        (root / name / "bits_per_pixel").write_text(f"{bpp}\n")
    (root / "fb0" / "stride").write_text("5120\n")
    drm = root / "drm" / "card1-HDMI-A-1"
    drm.mkdir(parents=True)
    (drm / "status").write_text("disconnected\n")
    m = desk.HdmiMirror.find(skip="/dev/fb1", graphics=root, drm=root / "drm")
    assert m.device == "/dev/fb0" and m.scale == 2 and m.at == (160, 40) and m.bpp == 32
    assert not m.plugged(100.0)
    (drm / "status").write_text("connected\n")
    assert not m.plugged(101.0) and m.plugged(106.0)                 # looked at again after 5 s
    frame = np.zeros((desk.H, desk.W, 3), dtype=np.uint8)
    frame[0, 0] = (255, 128, 1)
    fb = root / "fb.bin"
    fb.write_bytes(bytes(5120 * 720))
    with open(fb, "r+b", buffering=0) as f:
        m.write(f, frame)
    data = fb.read_bytes()
    at = 40 * 5120 + 160 * 4
    assert data[at:at + 8] == bytes([1, 128, 255, 0, 1, 128, 255, 0])   # BGRX, twice as wide
    assert data[at + 5120:at + 5124] == bytes([1, 128, 255, 0])          # and twice as tall
    assert data[at + 8:at + 12] == bytes(4) and data[:4] == bytes(4)
    m16 = desk.HdmiMirror("/dev/fb0", (480, 320), 16, 960)
    assert m16.pixels(frame)[0, 0] == (31 << 11) | (32 << 5) | 0       # RGB565 when the monitor runs 16-bit


def test_screen_writes():
    frame = Image.new("1", (128, 64))
    ImageDraw.Draw(frame).rectangle((0, 0, 9, 9), fill=1)
    out = desk.compose(frame, pressed="key2")
    assert out.size == (480, 320)
    assert out.getpixel((desk.SCREEN_AT[0] + 1, desk.SCREEN_AT[1] + 1)) == desk.FG     # lit pixel, scaled
    assert out.getpixel((240, 212)) == desk.KEY_ON                                      # key2 lit
    assert len(desk.rgb565(out)) == 480 * 320 * 2
    with tempfile.TemporaryDirectory() as tmp:                        # a file standing in for /dev/fb1
        fb = Path(tmp) / "fb1"
        fb.write_bytes(bytes(480 * 320 * 2))
        screen = desk.TftDisplay(str(fb))
        screen.show(frame)
        screen.press("key1")
        screen.fb.close()
        data = fb.read_bytes()
        assert len(data) == 480 * 320 * 2                             # written in place, never longer
        x, y = desk.SCREEN_AT[0] + 1, desk.SCREEN_AT[1] + 1
        lit = (((desk.FG[0] >> 3) << 11) | ((desk.FG[1] >> 2) << 5) | (desk.FG[2] >> 3)).to_bytes(2, "little")
        assert data[(y * 480 + x) * 2:(y * 480 + x) * 2 + 2] == lit


class RgbCapture:
    def __init__(self):
        self.image, self.theme = None, None

    def show_rgb(self, img):
        self.image = img.copy()


def test_touch_screens():
    """the desk UI by touch: tabs, a mixer slider dragged, a route tapped on and off, a theme picked"""
    import os
    os.environ.setdefault("FM1_SETTINGS", str(Path(tempfile.mkdtemp()) / "settings.json"))
    import bridge
    import deskui
    import sloopstyle
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.others = [{"id": 1, "name": "alsa_input.usb-EP-136", "label": "EP-136"},
                  {"id": 4, "name": "alsa_input.usb-SMK", "label": "SMK-37+VA"}]
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12                                             # no theme file: GREEN
    now = 0.0

    def tap(x, y, hold=0.0):
        ui.touch("down", x, y, now)
        ui.touch("up", x, y, now + hold)
        ui.render(now, force=True)
    def tab(name):                                                    # a tab, by the button that opens it
        box = next(w[0] for w in ui.widgets if w[3] == ("tab", name))
        tap((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    ui.render(now, force=True)
    assert app.display.image.size == (480, 320) and ui.theme == sloopstyle.Theme("GREEN")
    tab("MIX")
    assert ui.tab == "MIX"
    slider = next(w for w in ui.widgets if w[3] == ("slide", "u-smk37va"))
    box = slider[0]
    ui.touch("down", (box[0] + box[2]) // 2, box[3] - 10, now)        # the bottom: 0%
    assert app.mix_level("u-smk37va") == 0
    ui.touch("move", (box[0] + box[2]) // 2, box[1] + 10, now)        # dragged to the top: 200%
    ui.touch("up", (box[0] + box[2]) // 2, box[1] + 10, now)
    assert app.mix_level("u-smk37va") == 200
    tab("MIDI")
    cell = next(w for w in ui.widgets if w[3] == ("route", "BT>USB"))
    tap((cell[0][0] + cell[0][2]) // 2, (cell[0][1] + cell[0][3]) // 2)
    assert app.routes()["BT>USB"]["on"] is True                      # off at first: tapped on
    tap((cell[0][0] + cell[0][2]) // 2, (cell[0][1] + cell[0][3]) // 2, hold=0.8)
    assert app.screen == "route" and app.route_key == "BT>USB"            # held: its settings, a Studio page
    ui.render(now, force=True)
    assert not ui.classic and any(w[3] == "page-back" for w in ui.widgets)
    app.screen = "status"
    ui.render(now, force=True)
    tab("MORE")                                                       # then THEME: its page, AMBER tapped
    ui.more_top = 5                                                    # scrolled to the end of MORE
    ui.render(now, force=True)
    row = next(w for w in ui.widgets if w[3] == ("more", "THEME"))
    tap(row[0][0] + 20, row[0][1] + 10)
    assert ui.tab == "THEME"
    ui.render(now, force=True)
    assert {w[3] for w in ui.widgets} >= {("theme", n) for n in sloopstyle.ALL}   # every theme
    swatch = next(w for w in ui.widgets if w[3] == ("theme", "AMBER"))
    tap(swatch[0][0] + 20, swatch[0][1] + 10)
    assert app.state["desk_theme"] == "AMBER"
    ui.render(now + 5, force=True)
    assert ui.theme.name == "AMBER" and ui.tab == "THEME"              # still on the page, to try another
    swatch = next(w for w in ui.widgets if w[3] == ("theme", "KAWAII"))
    tap(swatch[0][0] + 20, swatch[0][1] + 10)
    ui.render(now + 10, force=True)
    assert ui.theme.name == "KAWAII" and ui.theme.bg == sloopstyle.EXTRA["KAWAII"][2]
    back = next(w for w in ui.widgets if w[3] == "theme-back")
    tap(back[0][0] + 20, back[0][1] + 10)
    assert ui.tab == "MORE"


def test_tab_bar():
    """eight tabs (MIXER, SAMPLER, XO-4, DECKS, RECORD with the reel-to-reel meter ...); the meters open from MIXER and the
    DAW from MIDI, each with a back button, their tab lit under them"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.render(0.0, force=True)
    assert [w[3][1] for w in ui.widgets if isinstance(w[3], tuple) and w[3][0] == "tab"] ==         ["HOME", "MIX", "PADS", "XO4", "DECKS", "REC", "MIDI", "MORE"] and deskui.TAB_LABEL["PADS"] == "SAMPLER"

    def press(key):
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        ui.touch("up", box[0] + 4, box[1] + 4, 0.0)
        ui.render(0.0, force=True)
    for there, button, page, back in (("MIX", "meters", "METER", "meter-back"), ("MIDI", "daw", "DAW", "daw-back")):
        press(("tab", there))
        press(button)
        assert ui.tab == page and deskui.PARENT[page] == there
        assert any(w[3] == ("tab", there) for w in ui.widgets)      # the bar's still there, its tab lit
        press(back)
        assert ui.tab == there
    assert app.screen == "status"                                    # (the meters' reader let go)
    toggled = []
    app.toggle_recording = lambda: toggled.append(True)
    press(("tab", "REC"))                                            # RECORD: its own tab, the reels' levels on
    assert ui.tab == "REC" and app.screen == "meter" and deskui.TAB_LABEL["REC"] == "RECORD" and deskui.TAB_LABEL["MIX"] == "MIXER"
    press("rec-go")
    assert toggled
    press("rec-takes")
    assert app.screen == "pick" or app.message == "No recordings yet"   # the takes (a Studio page), or none
    assert "RECORDINGS" not in [m[0] for m in deskui.MORE]
    for tab in ("REC", "PADS"):                                     # RECORD and SAMPLER: full screen, as DECKS
        app.screen = "status"
        ui.open_tab(tab)
        ui.render(0.0, force=True)
        assert not any(isinstance(w[3], tuple) and w[3][0] == "tab" for w in ui.widgets), tab
    app.screen = "status"
    ui.open_tab("HOME")
    ui.render(0.0, force=True)
    opened = []
    ui.open_decks = lambda: opened.append(True) or setattr(ui, "tab", "DECKS")   # (no decks program here)
    press(("tab", "DECKS"))                                          # the DJ decks: a tab, no longer in MORE
    assert opened and ui.tab == "DECKS" and "DJ DECKS" not in [m[0] for m in deskui.MORE]
    app.pads = None
    for tab in ("MIX", "PADS", "REC", "MIDI", "MORE"):              # every tab: < HOME, top left
        app.screen = "status"
        ui.open_tab(tab)
        ui.render(0.0, force=True)
        box = next(w[0] for w in ui.widgets if w[3] == "home")
        assert box[0] < 10 and box[2] <= 70, (tab, box)
        press("home")
        assert ui.tab == "HOME", tab


def test_four_usb_devices():
    """all four of the Studio's USB ports with sound and MIDI: every device its own mixer channel (two alike
    numbered), all of them and the sampler in Record parts (six sources), up to eight MIDI controllers"""
    import blemidi
    import bridge
    import deskui
    import meters

    def node(i, label, name):
        return {"type": "PipeWire:Interface:Node", "id": i, "info": {"props": {
            "media.class": "Audio/Source", "node.name": name, "alsa.card_name": label,
            "api.alsa.path": f"front:{i}"}}}
    objects = [node(10, "EP-136", "alsa_input.usb-EP-136-a"), node(11, "EP-136", "alsa_input.usb-EP-136-b"),
               node(12, "SMK-37+VA", "alsa_input.usb-SMK"), node(13, "Scarlett 2i2", "alsa_input.usb-Focusrite"),
               {"type": "PipeWire:Interface:Node", "id": 14, "info": {"props": {
                   "media.class": "Audio/Source", "node.name": "fm1-sampler"}}}]
    sink, others = bridge.pick_nodes(objects)
    assert sink is None and len(others) == 5
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.others = others
    keys = [k for k, _ in app.mix_channels()]
    assert len(set(keys)) == 5
    names = [app.channel_name(k) for k in keys]
    assert names[:2] == ["EP-136", "EP-136 #2"] and "SCARLETT 2" in names[3] and names[4] == "SAMPLER"
    assert len(meters.PARTS_MAP) // 2 >= len(keys)                    # Record parts: room for every source
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIX")
    ui.render(0.0, force=True)
    assert {("slide", k) for k in keys} <= {w[3] for w in ui.widgets}  # a fader each
    b = blemidi.MidiBridge(net=True)
    assert b.controllers.MAX == 8 and blemidi.MidiBridge().controllers.MAX == 4


def test_flow_walk_fixes():
    """from the UI flow walk: header buttons touch the header's whole height, MORE fits one screen, HOME's
    SPEAKER row opens the speaker list, the tempo shows the one it plays at"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    scans = []
    app.start_scan = lambda: scans.append(True)
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIX")
    ui.render(0.0, force=True)
    meters_box = next(w[0] for w in ui.widgets if w[3] == "meters")
    assert meters_box[1] == 0 and meters_box[3] >= deskui.HDR_H                # the header's whole height
    ui.open_tab("MORE")
    ui.render(0.0, force=True)
    assert {m[0] for m in deskui.MORE} <= {w[3][1] for w in ui.widgets if isinstance(w[3], tuple)
                                           and w[3][0] == "more"}               # all of it, no scrolling
    ui.open_tab("HOME")
    ui.render(0.0, force=True)
    row = next(w[0] for w in ui.widgets if w[3] == ("row", "spk"))
    ui.touch("down", row[0] + 60, row[1] + 10, 0.0)
    ui.touch("up", row[0] + 60, row[1] + 10, 0.0)
    assert scans
    app.state["clock_mode"], app.state["bpm"] = "follow", 97
    assert ui.tempo_text() == "97 BPM"                                         # nothing to follow: its own


def test_theme_from_file_has_tuples():
    """a theme read back from its JSON file draws: its colours are tuples (Pillow 11 refuses lists: the
    Studio crashed on its first start with FM-1 A's theme saved)"""
    import json
    import sloopstyle
    t = sloopstyle.theme_load(json.loads(json.dumps(sloopstyle.theme_dict(sloopstyle.Theme("AMBER")))))
    assert all(isinstance(c, tuple) for c in t.c + t.track + [t.bg, t.hi] + t.dim + t.grey)


def test_midi_tab_with_sampler_and_daw():
    """the MIDI tab with the sampler (SMP) and a DAW (NET). It crashed the app on the Studio (2026-10-24: no
    label for SMP), restarting it every time MIDI was opened"""
    import bridge
    import deskui

    class Midi:
        pads, net, mcu, clock = True, ["MacBook"], None, None
        controllers = ["Clipper"]

        def set_routes(self, routes):
            pass
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings, app.midi = (lambda: None), Midi()
    sources, dests = app.matrix_lists()
    assert "SMP" in dests and "NET" in dests and "NET" in sources and "SMP" not in sources
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIDI")
    ui.render(0.0, force=True)                                       # draws: no KeyError
    assert ("route", "USB>SMP") in [w[3] for w in ui.widgets] and ("route", "NET>BT") in [w[3] for w in ui.widgets]


def test_each_usb_midi_device_its_own_route():
    """the Studio: each USB MIDI device a row and column of its own, by name (the SMK-37 running Clipper and the
    Sidekick, EP-136), USB's routes to start with, routed apart, kept when unplugged; the Pocket keeps USB"""
    import blemidi
    import bridge
    import deskui
    assert blemidi.route_default("U:EP-136>SMP")["on"] and not blemidi.route_default("Box>U:EP-136")["on"]
    assert not blemidi.route_default("U:Clipper>U:EP-136")["on"]               # device to device: off at first
    assert blemidi.matrix(["Clipper", "EP-136"])[0] == ("BT", "U:Clipper", "U:EP-136", "NET", "XO4", "Box")
    assert blemidi.matrix()[0] == blemidi.SOURCES                               # the Pocket: USB, as one
    cleaned = blemidi.clean_routes({"U:EP-136>SMP": {"on": False}})
    assert cleaned["U:EP-136>SMP"]["on"] is False and "BT>SMP" in cleaned
    for bad in ({"U:EP-136>U:EP-136": {}}, {"X:y>SMP": {}}, {"U:>SMP": {}}):
        try:
            blemidi.clean_routes(bad)
            assert False, bad
        except ValueError:
            pass

    class Pads:
        def __init__(self):
            self.sent = []

        def send(self, msg):
            self.sent.extend(msg[1])
    b = blemidi.MidiBridge(net=True, pads=Pads())                              # the MIDI process, the Studio's
    to_dev = []
    b.controllers.send_to = lambda name, m: to_dev.append((name, list(m)))
    b.controllers.names = lambda: ["Clipper", "EP-136"]
    b.to_ble = lambda m: None
    b.set_routes({"U:EP-136>SMP": {"on": False}})
    b.from_controllers(bytes([0x90, 60, 100]), "EP-136")                     # the Sidekick: not to the pads
    assert b.pads.sent == []
    b.from_controllers(bytes([0x90, 62, 100]), "Clipper")                    # the SMK-37: to the pads
    assert b.pads.sent == [[0x90, 62, 100]]
    b.set_routes({"NET>U:Clipper": {"on": True}})
    b.from_net(bytes([0x90, 64, 90]))                                         # the DAW to the SMK-37 alone
    assert [n for n, _ in to_dev] == ["Clipper"]

    class Midi:
        pads, net, mcu, clock, split = True, [], None, None, True
        controllers = ["Clipper", "EP-136"]
        peer, enabled, error = None, True, None

        def set_routes(self, routes):
            self.last = routes
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings, app.midi = (lambda: None), Midi()
    sources, dests = app.matrix_lists()
    assert "U:EP-136" in sources and "U:Clipper" in dests and "USB" not in sources + dests
    app.set_route_of("U:EP-136>SMP", on=False)
    app.midi.controllers = ["Clipper"]                                        # the Sidekick unplugged
    app.set_route_of("U:Clipper>SMP", on=False)
    assert app.state["routes"]["U:EP-136>SMP"]["on"] is False                  # kept for when it's back
    app.midi.controllers = ["Clipper", "EP-136"]
    assert app.routes()["U:EP-136>SMP"]["on"] is False
    app.route_key = "U:EP-136>SMP"
    assert app.route_title() == "EP-136 > SMP"
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIDI")
    ui.render(0.0, force=True)
    assert ("route", "U:Clipper>SMP") in [w[3] for w in ui.widgets]
    web = app.web_status()                                                    # the web app gets the same grid
    assert "U:EP-136" in web["matrix"]["sources"] and "U:EP-136>SMP" in web["routes"]
    app.midi.split = False                                                    # the Pocket: USB as before
    assert "USB" in app.matrix_lists()[0]


def test_meters_steady():
    """the level bars rise at once and fall back at FALL dB a second whatever the frame rate; the screen gets
    each changed strip on its own (a meter's two bars, not the scale between them)"""
    import deskmeters
    import meters as m
    dm = deskmeters.DeskMeters()
    assert dm.ballistic(0, 32768 * 0.5, 0.05) > -7                   # -6 dBFS: at once
    a = dm.ballistic(0, 1, 0.1)                                       # silence: falls 2.6 dB in 0.1 s
    assert abs(a - (dm.shown[0])) < 1e-9 and -9 < a < -8
    b = deskmeters.DeskMeters()
    b.ballistic(0, 32768 * 0.5, 0.05)
    for _ in range(4):                                                # four frames of 0.025 s = one of 0.1 s
        b.ballistic(0, 1, 0.025)
    assert abs(b.shown[0] - a) < 1e-6
    assert m.FLOOR == dm.ballistic(1, 0, 0.1)
    rows = [False] * 320
    for r in list(range(60, 120)) + list(range(130, 190)) + [195]:
        rows[r] = True
    assert desk.changed_strips(rows) == [(60, 120), (130, 196)]     # (a 10-row gap kept apart, a 4-row one joined)


def test_loopback_follows_a_source_back():
    """a USB device off USB for a few seconds comes back as a new PipeWire node of the same name: its loopback (left
    running, unlinked) is stopped so the next ensure starts it afresh; the same for a speaker back anew"""
    import bridge

    class Proc:
        def __init__(self, *a, **k):
            self.alive = True

        def poll(self):
            return None if self.alive else 0

        def terminate(self):
            self.alive = False

        def wait(self, timeout=None):
            return 0
    started = []
    real = bridge.subprocess.Popen, bridge.set_rate
    bridge.subprocess.Popen = lambda cmd, **k: started.append(cmd) or Proc()
    bridge.set_rate = lambda rate: None

    def node(i, name):
        return {"type": "PipeWire:Interface:Node", "id": i, "info": {"props": {"node.name": name}}}
    ep, jbl = "alsa_input.usb-teenage_engineering_EP-136-00.analog-stereo", "bluez_output.20_18_5B_EF_AA_B0.1"
    try:
        loop = bridge.Loopback()
        loop.ensure(ep, jbl, "fm1-mix-u-ep136")
        assert not loop.follow([node(87, ep), node(110, jbl)])       # first look: its ends noted
        assert not loop.follow([node(87, ep), node(110, jbl)])       # the same: nothing to do
        assert not loop.follow([node(110, jbl)])                      # the device gone just now: left to ensure
        assert loop.follow([node(95, ep), node(110, jbl)]) and not loop.running()   # back as a new node
        loop.ensure(ep, jbl, "fm1-mix-u-ep136")
        assert len(started) == 2 and loop.running()                   # started afresh
        assert not loop.follow([node(95, ep), node(110, jbl)])
        assert loop.follow([node(95, ep), node(141, jbl)])           # the speaker reconnected: the same
        copy = bridge.Loopback()                                      # a copy off the speaker's monitor
        copy.ensure("monitor:" + jbl, "alsa_output.jack", "fm1-phones")
        assert not copy.follow([node(141, jbl), node(47, "alsa_output.jack")])
        assert copy.follow([node(150, jbl), node(47, "alsa_output.jack")])
    finally:
        bridge.subprocess.Popen, bridge.set_rate = real


def test_lost_input_pair_relinked():
    """an interface's chosen pair (the Sidekick's 1-2) whose links didn't get made (a busy restart) is linked
    again on the next look at PipeWire, at most every 5 s; linked, nothing is done"""
    import bridge
    loop = bridge.Loopback()
    loop.links = [("alsa_input.ep136", "capture_FL", "fm1-in-fm1-mix-u-ep136", "input_FL"),
                  ("alsa_input.ep136", "capture_FR", "fm1-in-fm1-mix-u-ep136", "input_FR")]
    loop.started = 100.0
    loop.running = lambda: True
    made = []
    real, bridge.link_ports = bridge.link_ports, lambda links: made.append(list(links))
    try:
        node = {"type": "PipeWire:Interface:Node", "id": 50,
                "info": {"props": {"node.name": "fm1-in-fm1-mix-u-ep136"}}}
        assert not loop.heal([node], now=101.0)                       # too soon after start
        assert loop.heal([node], now=103.0) and len(made) == 1        # no links: made again
        assert not loop.heal([node], now=105.0)                       # (not again within 5 s)
        links = [{"type": "PipeWire:Interface:Link", "id": 60, "info": {"input-node-id": 50, "state": "active"}},
                 {"type": "PipeWire:Interface:Link", "id": 61, "info": {"input-node-id": 50, "state": "active"}}]
        assert not loop.heal([node] + links, now=120.0) and len(made) == 1   # linked: nothing to do
        idle = [dict(link, info=dict(link["info"], state="paused")) for link in links]
        assert not loop.heal([node] + idle, now=130.0)                # both paused: nothing playing, left alone
        destroyed = []
        real_run, bridge.run = bridge.run, lambda cmd, timeout=None: (destroyed.append(cmd), (0, ""))[1]
        try:
            one_stuck = [links[0], idle[1]]                           # the right side stuck while the left plays
            assert loop.heal([node] + one_stuck, now=140.0) and len(made) == 2
            assert destroyed == [["pw-cli", "destroy", "61"]]
        finally:
            bridge.run = real_run
    finally:
        bridge.link_ports = real


def test_frames_paced_to_the_spi_link():
    """no frame is written while the last is still going to the screen (tearing): its time from the rows sent
    and the link's speed (the dtoverlay's speed=)"""
    cfg = Path(tempfile.mkdtemp()) / "config.txt"
    cfg.write_text("dtparam=spi=on\ndtoverlay=piscreen,speed=32000000,rotate=90\n")
    assert desk.spi_hz(cfg) == 32_000_000 and desk.spi_hz(cfg.parent / "none.txt") == 16_000_000
    with tempfile.TemporaryDirectory() as tmp:
        fb = Path(tmp) / "fb"
        fb.write_bytes(bytes(480 * 320 * 2))
        screen = desk.TftDisplay(str(fb))
        screen.hz = 16_000_000
        img = Image.new("RGB", (480, 320), (10, 20, 30))
        screen.show_rgb(img)
        full = screen.busy_until - time.monotonic()
        assert 0.15 < full < 0.25                                    # 320 rows at 16 MHz, + 1/30 s
        t0 = time.monotonic()
        img.paste((200, 0, 0), (0, 100, 480, 110))                    # 10 rows changed
        screen.show_rgb(img)
        assert time.monotonic() - t0 >= full - 0.02                   # waited for the first to be sent
        assert screen.busy_until - time.monotonic() < 0.06           # 10 rows: quick
        screen.fb.close()


def test_studio_has_no_tuner():
    """the Studio's meters step past the tuner both ways and count without it; left on it, the next shows"""
    import bridge
    import deskui
    import meters
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("METER")                                             # (meters change while their screen is open)
    seen = []
    for _ in range(len(meters.METERS) + 2):
        ui.next_meter(1)
        seen.append(meters.METERS[app.meter_index()])
    assert "Tuner" not in seen and len(set(seen)) == len(meters.METERS) - 1
    for _ in range(len(meters.METERS) + 2):
        ui.next_meter(-1)
        assert meters.METERS[app.meter_index()] != "Tuner"
    app.state["meter"] = meters.METERS.index("Tuner")
    ui.open_tab("METER")
    ui.render(0.0, force=True)
    assert meters.METERS[app.meter_index()] != "Tuner"


def test_every_meter_draws():
    """each of the eleven desk meters, with sound (a chord) and with silence, without an error"""
    import math
    import numpy as np
    import deskmeters
    import meters
    import sloopstyle
    meters.load_numpy()
    t = np.arange(meters.RECENT_N) / meters.RATE
    wave = (sum(np.sin(2 * math.pi * f * t) for f in (220, 277, 330)) * 6000).astype("<i2")
    loud = np.stack([wave, wave // 2], axis=1)

    class Reader:
        def __init__(self, x):
            self.x = x

        def take(self):
            return self.x[-512:], self.x

    class Clock:
        clock = {"bpm": 120, "tempo": 120.0, "source": "box", "playing": True, "bar": 0.0}
        notes, chans = [60, 64, 67], 1 | (1 << 9)

    class App:
        source, midi, tape_done, last_activity = {"name": "x"}, Clock(), 0.4, 0.0

        def capture_target(self):
            return "monitor:x"
        recorder = type("R", (), {"recording": lambda self: True})()

        def __init__(self, i, x):
            self.i, self.levels = i, Reader(x)

        def meter_index(self):
            return self.i
    for x in (loud, np.zeros((meters.RECENT_N, 2), dtype="<i2")):
        dm = deskmeters.DeskMeters()
        for i, name in enumerate(meters.METERS):
            img = Image.new("RGB", (480, 320))
            for k in range(3):
                dm.draw(App(i, x), img, (0, 35, 480, 275), sloopstyle.Theme("AMBER"), 1.0 + k * 0.1)
    assert dm.tune is None                                            # silence: no note


def test_native_pages():
    """no Pocket screens on the Studio: a settings section, a value with - / +, a confirmation held, back"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12

    def press(key, now=0.0, hold=0.0):
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, now)
        if hold:
            ui.render(now + hold, force=True)                          # still held: the confirm fires
        else:
            ui.touch("up", box[0] + 4, box[1] + 4, now)
        ui.render(now + hold, force=True)
    ui.open_tab("MORE")
    ui.render(0.0, force=True)
    press(("more", "PLAYING"))
    assert app.screen == "settings" and app.settings_menu == "play"
    rows = [r[0] for r in app.settings_rows()]
    press(("row", rows.index("tempo")))                                # tempo: being edited, - / + on its row
    assert app.editing == "tempo"
    bpm = app.state["bpm"]
    press(("plus", rows.index("tempo")))
    press(("plus", rows.index("tempo")))
    assert app.state["bpm"] == bpm + 2
    press(("row", rows.index("tempo")))                                # tapped again: done
    assert app.editing is None
    press("page-back")                                                 # out of the section: MORE again
    assert app.screen == "status" and ui.tab == "MORE"
    ui.more_top = 6
    ui.render(0.0, force=True)
    done = []
    app.shutdown = lambda: done.append(True)
    press(("more", "SHUT DOWN"))
    assert app.screen == "confirm"
    press("confirm", now=10.0, hold=0.5)                               # let go too soon: nothing
    assert not done
    press("confirm", now=20.0, hold=2.1)                               # held 2 s: confirmed
    assert done


def test_daw_surface():
    """the DAW tab: Kraken's names and faders shown, a fader dragged and PLAY pressed sent back as Mackie Control"""
    import bridge
    import deskui

    class Midi:
        enabled, error, peer, net, notes, chans, clock = True, None, None, ["Mac"], [], 0, None

        def __init__(self):
            names = "".join(f"{n:<6} " for n in ["BASS", "KEYS"] + [""] * 6)
            self.mcu = {"faders": [8192] * 9, "leds": [0x5E], "lcd": [names, " " * 56], "seen": 1.0}
            self.sent = []

        def mcu_send(self, messages):
            self.sent += messages
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.midi = Midi()
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("DAW")
    ui.render(0.0, force=True)
    fader = next(w[0] for w in ui.widgets if w[3] == ("fader", 1))
    ui.touch("down", (fader[0] + fader[2]) // 2, fader[3] - 10, 0.0)              # KEYS to the bottom
    ui.touch("up", 0, 0, 0.0)
    play = next(w[0] for w in ui.widgets if w[3] == ("daw", "play"))
    ui.touch("down", play[0] + 5, play[1] + 5, 0.0)
    ui.touch("up", play[0] + 5, play[1] + 5, 0.0)
    assert app.midi.sent == [bytes([0x90, 0x69, 127]), bytes([0xE1, 0, 0]),     # finger on KEYS' fader, moved,
                             bytes([0x90, 0x69, 0]), bytes([0x90, 0x5E, 127])]    # lifted; then PLAY
    pan = next(w[0] for w in ui.widgets if w[3] == ("pan+", 0))
    ui.touch("down", pan[0] + 2, pan[1] + 2, 0.0)
    ui.touch("up", pan[0] + 2, pan[1] + 2, 0.0)
    assert app.midi.sent[-1] == bytes([0xB0, 0x10, 2])                          # BASS panned right


def test_xo4_tab():
    """XO-4's tab, full screen: patterns, tracks, steps with chords from the note keys, a step's VEL and LEN, the
    drums' pads, octave, key and scale, a track cleared; what's tapped sounds while stopped; the song is kept"""
    import bridge
    import deskui
    import sloopstyle
    import xo4

    class XO4:
        step = pattern = queued = None

        def __init__(self):
            self.sent = []

        def send(self, *msg):
            self.sent.append(msg)

    class Pads:
        sounding, step = [], None

        def __init__(self):
            self.sent = []

        def send(self, *msg):
            self.sent.append(msg)

    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.xo4, app.pads = XO4(), Pads()
    app.state["kit"] = {"name": "K", "pads": [{"sample": ""}] * 16}
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12

    def press(key, hold=False):
        ui.render(0.0, force=True)
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        if hold:
            ui.touch("move", box[0] + 4, box[1] + 4, 0.7)       # held past 0.6 s: its long press
        ui.touch("up", box[0] + 4, box[1] + 4, 0.7 if hold else 0.0)
        ui.render(0.0, force=True)

    def song():
        return app.song()

    press(("tab", "XO4"))
    assert ui.tab == "XO4" and not any(isinstance(w[3], tuple) and w[3][0] == "tab" for w in ui.widgets)   # full
    assert {("xo4-pat", p) for p in xo4.PATTERNS} <= {w[3] for w in ui.widgets}
    press(("xo4-pat", "B"))                                         # stopped: B plays and is edited at once
    assert song()["pattern"] == "B" and ("pick", "B") in app.xo4.sent
    press(("xo4-track", 1))                                         # SYN 1
    press(("xo4-step", 0))                                          # an empty step: the last notes, selected
    step = song()["patterns"]["B"][1]["steps"][0]
    assert step["notes"] == [60] and ui.xo4_step == 0 and ("audition", 1, [60], 100) in app.xo4.sent
    press(("xo4-key", 64))                                          # E4 and G4 added: a chord
    press(("xo4-key", 67))
    assert song()["patterns"]["B"][1]["steps"][0]["notes"] == [60, 64, 67]
    press(("xo4-vel", "+"))
    press(("xo4-len", "+"))
    step = song()["patterns"]["B"][1]["steps"][0]
    assert step["vel"] == 108 and step["len"] == 1.5
    press(("xo4-step", 4))                                          # a new step gets the chord
    assert song()["patterns"]["B"][1]["steps"][4]["notes"] == [60, 64, 67] and ui.xo4_step == 4
    press(("xo4-step", 4))                                          # tapped again: emptied
    assert song()["patterns"]["B"][1]["steps"][4] is None and ui.xo4_step is None
    press(("xo4-step", 0), hold=True)                               # held: emptied
    assert song()["patterns"]["B"][1]["steps"][0] is None
    press("xo4-len+")
    assert song()["patterns"]["B"][1]["len"] == 17
    press(("xo4-page", 1))                                          # 17 steps: a second page
    assert ui.xo4_page == 1 and ("xo4-step", 16) in {w[3] for w in ui.widgets}
    press("xo4-root")
    press("xo4-scale")
    assert song()["root"] == 1 and song()["scale"] == "MINOR"
    press("xo4-oct-")
    assert ui.xo4_oct[1] == 3
    keys = [w[3][1] for w in ui.widgets if isinstance(w[3], tuple) and w[3][0] == "xo4-key"]
    assert len(keys) == 14
    assert keys == xo4.scale_notes(song(), 4 * 12 + 1, 14)         # C#3 minor, from the octave's root up
    press(("xo4-track", 0))                                         # DRUMS: a pad picked (heard), steps toggle it
    press(("xo4-pad", 3))
    assert ui.xo4_pad == 3 and app.pads.sent[-1] == ("tap", 3, 100)
    press(("xo4-step", 2))
    press(("xo4-pad", 5))
    press(("xo4-step", 2))
    assert song()["patterns"]["B"][0]["steps"][2]["notes"] == [3, 5]
    press(("xo4-step", 2))
    assert song()["patterns"]["B"][0]["steps"][2]["notes"] == [3]
    box = next(w[0] for w in ui.widgets if w[3] == "xo4-clear")     # HOLD CLR: held to confirm, as everywhere
    ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
    ui.render(deskui.HOLD + 0.1)
    ui.touch("up", box[0] + 4, box[1] + 4, deskui.HOLD + 0.1)
    assert song()["patterns"]["B"][0]["steps"][2] is None
    app.xo4.step, app.xo4.pattern = 18, "B"                         # the playhead lit while playing
    app.playing = True
    app.state["clock_mode"] = "box"
    ui.render(0.0, force=True)
    assert ui.app.display.image.size == (480, 320)
    assert sloopstyle.ALL                                           # (drawn in the theme's colours)
    press("xo4-home")
    assert ui.tab == "HOME"


def test_home_tempo():
    """HOME's tempo - / +: a tap is 1 BPM, a hold 10, within 30-300; following another clock, they leave it be"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, bpm=120))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12

    def press(key, hold=False):
        ui.render(0.0, force=True)
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        if hold:
            ui.touch("move", box[0] + 4, box[1] + 4, 0.7)
        ui.touch("up", box[0] + 4, box[1] + 4, 0.7 if hold else 0.0)
    press(("tempo", "+"))
    assert app.state["bpm"] == 121
    press(("tempo", "-"), hold=True)
    assert app.state["bpm"] == 111
    app.state["bpm"] = 298
    press(("tempo", "+"), hold=True)
    assert app.state["bpm"] == 300                                  # (no further than 300)
    app.state["clock_mode"] = "follow"
    app.midi = type("M", (), {"clock": {"bpm": 97, "playing": True}, "set_clock": lambda self, *a: None})()
    press(("tempo", "-"))
    assert app.state["bpm"] == 300 and "Following" in app.message
