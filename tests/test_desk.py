"""The desk box (Pi 3/4 + 3.5" touchscreen): which build a box is, the touch buttons, the screen writes.
No touchscreen needed (needs Pillow and numpy)."""

import io
import json
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fm1-bt-bridge"))

from PIL import Image, ImageDraw  # noqa: E402

import desk  # noqa: E402
import device  # noqa: E402
import sequencer  # noqa: E402

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
    assert "fast" not in box["can"]                                   # a Pi 3: the voices as they were
    assert "fast" in device.detect(model="Raspberry Pi 4 Model B Rev 1.5", screen=TFT)["can"]
    assert device.fast("Raspberry Pi 5 Model B Rev 1.0") and device.fast("Raspberry Pi 400 Rev 1.0")
    assert not device.fast(ZERO) and not device.fast("Raspberry Pi 3 Model B Plus Rev 1.3") and not device.fast("")
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
    with tempfile.TemporaryDirectory() as tmp:                       # the 3.5" HDMI touchscreen: HDMI at 720x480
        root = Path(tmp)
        (root / "fb0").mkdir()
        (root / "fb0" / "virtual_size").write_text("720,480\n")
        (root / "fb0" / "name").write_text("vc4drmfb\n")
        assert device.touchscreen(root) == ("/dev/fb0", 720, 480) and device.hdmi35(720, 480)
        (root / "fb1").mkdir()                                       # with an SPI screen too: the SPI one
        (root / "fb1" / "virtual_size").write_text("480,320\n")
        (root / "fb1" / "name").write_text("fb_ili9486\n")
        assert device.touchscreen(root) == ("/dev/fb1", 480, 320)
    with tempfile.TemporaryDirectory() as tmp:                       # its frames: 1.5x, turned round
        fb = Path(tmp) / "fb"
        fb.write_bytes(bytes(720 * 480 * 2))
        scaled = desk.ScaledFb(str(fb), (720, 480), flip=True)
        scaled.seek(0)
        scaled.write(b"\x34\x12")                                    # the top-left pixel...
        scaled.out.close()
        data = fb.read_bytes()
        assert data[-2:] == b"\x34\x12" and data[:2] == b"\0\0"       # ...bottom-right on the panel
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
    dac = {"type": "PipeWire:Interface:Node", "id": 12, "info": {"props": {      # a DAC HAT: the master, not the jack
        "media.class": "Audio/Sink", "node.name": "alsa_output.platform-soc_sound.stereo-fallback",
        "node.description": "Built-in Audio Stereo", "alsa.card_name": "BossDAC"}}}   # (as the Studio shows it)
    assert bridge.jack_node(objects + [dac])["id"] == 9
    assert bridge.dac_node(objects + [dac]) == {"id": 12, "name": "alsa_output.platform-soc_sound.stereo-fallback",
                                                 "label": "DAC"}
    assert bridge.dac_node(objects) is None
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
    m15 = desk.HdmiMirror("/dev/fb0", (720, 480), 16, 1440)           # 720x480 (a boot line's): 1.5x, the whole of it
    assert m15.scale == 1.5 and m15.at == (0, 0) and m15.pixels(frame).shape == (480, 720)
    assert m15.pixels(frame)[0, 0] == m15.pixels(frame)[1, 1] != m15.pixels(frame)[2, 2]


def test_find_touch():
    """the touchscreen's input device; two touch chips listed (an old ads7846 overlay on spi0.0 left beside
    piscreen's, on a box set up before): the screen's own, spi0.1, whichever comes first"""
    block = lambda n, spi: (f'I: Bus=001c\nN: Name="ADS7846 Touchscreen"\nP: Phys={spi}/input0\n'   # noqa: E731
                            f"S: Sysfs=/devices/platform/soc/3f204000.spi/spi_master/spi0/{spi}/input/input{n}\n"
                            f"H: Handlers=mouse{n} event{n} \nB: EV=b\n")
    root = Path(tempfile.mkdtemp(prefix="fm1-touch-"))
    devices = root / "devices"
    devices.write_text(block(0, "spi0.0") + "\n" + block(1, "spi0.1"))
    assert desk.find_touch(devices) == "/dev/input/event1"
    devices.write_text(block(0, "spi0.1"))
    assert desk.find_touch(devices) == "/dev/input/event0"
    devices.write_text('I: Bus=0003\nN: Name="USB Keyboard"\nH: Handlers=kbd event3 \n')
    assert desk.find_touch(devices) is None

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
    import xoxostyle
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.others = [{"id": 1, "name": "alsa_input.usb-EP-136", "label": "EP-136"},
                  {"id": 4, "name": "alsa_input.usb-SMK", "label": "SMK-37+VA"}]
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12                                             # no theme file: XOXO
    now = 0.0

    def tap(x, y, hold=0.0):
        ui.touch("down", x, y, now)
        ui.touch("up", x, y, now + hold)
        ui.render(now, force=True)
    def tab(name):                                                    # a tab, by the button that opens it
        box = next(w[0] for w in ui.widgets if w[3] == ("tab", name))
        tap((box[0] + box[2]) // 2, (box[1] + box[3]) // 2)
    ui.render(now, force=True)
    assert app.display.image.size == (480, 320) and ui.theme == xoxostyle.Theme("XOXO")
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
    tab("MORE")                                                       # then STUDIO SETTINGS > THEME: TOXIC tapped
    ui.render(now, force=True)
    assert ("more", "THEME") not in {w[3] for w in ui.widgets}          # (in STUDIO SETTINGS now)
    row = next(w for w in ui.widgets if w[3] == ("more", "STUDIO SETTINGS"))
    tap(row[0][0] + 20, row[0][1] + 10)
    assert ui.tab == "SETTINGS"
    ui.render(now, force=True)
    assert {("more", n) for n in ("WI-FI", "THEME", "TOUCH SETUP", "ABOUT")} <= {w[3] for w in ui.widgets}
    row = next(w for w in ui.widgets if w[3] == ("more", "THEME"))
    tap(row[0][0] + 20, row[0][1] + 10)
    assert ui.tab == "THEME"
    ui.render(now, force=True)
    assert {w[3] for w in ui.widgets} >= {("theme", n) for n in xoxostyle.ALL}   # every theme
    swatch = next(w for w in ui.widgets if w[3] == ("theme", "TOXIC"))
    tap(swatch[0][0] + 20, swatch[0][1] + 10)
    assert app.state["desk_theme"] == "TOXIC"
    ui.render(now + 5, force=True)
    assert ui.theme.name == "TOXIC" and ui.tab == "THEME"              # still on the page, to try another
    swatch = next(w for w in ui.widgets if w[3] == ("theme", "KAWAII"))
    tap(swatch[0][0] + 20, swatch[0][1] + 10)
    ui.render(now + 10, force=True)
    assert ui.theme.name == "KAWAII" and ui.theme.bg == xoxostyle.THEMES["KAWAII"][2]
    back = next(w for w in ui.widgets if w[3] == "theme-back")
    tap(back[0][0] + 20, back[0][1] + 10)
    assert ui.tab == "SETTINGS"                                        # back to STUDIO SETTINGS
    ui.render(now, force=True)
    back = next(w for w in ui.widgets if w[3] == "settings-back")
    tap(back[0][0] + 20, back[0][1] + 10)
    assert ui.tab == "MORE"


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
    import xoxostyle
    t = xoxostyle.theme_load(json.loads(json.dumps(xoxostyle.theme_dict(xoxostyle.Theme("TOXIC")))))
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
    assert blemidi.matrix(["Clipper", "EP-136"])[0] == ("BT", "U:Clipper", "U:EP-136", "NET", "SEQ", "Box")
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
    b.sq_in = True                                                            # (XO-4's MIDI IN on)
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
        pocket = bridge.Loopback()                                    # back as the same id (PipeWire reuses
        pocket.ensure("fm1-pocket", jbl, "fm1-mix-u-pocket")          # them), a new serial: still restarted
        serial = lambda i, name, s: {"type": "PipeWire:Interface:Node", "id": i,   # noqa: E731
                                     "info": {"props": {"node.name": name, "object.serial": s}}}
        assert not pocket.follow([serial(150, "fm1-pocket", 900), serial(141, jbl, 800)])
        assert pocket.follow([serial(150, "fm1-pocket", 931), serial(141, jbl, 800)])
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
    cfg.write_text("dtparam=spi=on\ndtoverlay=xoxo35,speed=24000000,rotate=90\n")   # the Studio's own overlay
    assert desk.spi_hz(cfg) == 24_000_000
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
    import xoxostyle
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
                dm.draw(App(i, x), img, (0, 35, 480, 275), xoxostyle.Theme("TOXIC"), 1.0 + k * 0.1)
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


def test_about():
    """MORE > ABOUT: the version, and QR codes for the code, the website and this Studio's web app (its address
    now); with no network, no web app code and a note to join Wi-Fi; the boot screen shows the version too"""
    import bridge
    import deskabout
    import deskboot
    import deskui
    import xoxostyle

    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    real = deskabout.lan_address
    drawn = []
    real_qr = ui.draw_qr
    ui.draw_qr = lambda img, d, box, url: (drawn.append(url), real_qr(img, d, box, url))
    try:
        deskabout.lan_address = lambda: "192.168.1.20"
        ui.open_tab("SETTINGS")
        ui.render(0.0, force=True)
        box = next(w[0] for w in ui.widgets if w[3] == ("more", "ABOUT"))
        ui.touch("down", box[0] + 4, box[1] + 4, 0.0)
        ui.touch("up", box[0] + 4, box[1] + 4, 0.0)
        ui.render(0.0, force=True)
        assert ui.tab == "ABOUT"
        assert drawn == ["https://github.com/xoxoaudiolabs/XOXO-Studio", "https://xoxoaudiolabs.com",
                         "http://192.168.1.20/"]
        modules = deskabout.qr_modules(drawn[2])
        assert modules and len(modules) == len(modules[0]) >= 21 + 4      # a real code, its quiet zone around it
        deskabout.lan_address = lambda: None                               # no network: no web app code
        ui.about_ip_at, drawn[:] = -1e9, []
        ui.render(0.0, force=True)
        assert drawn[2] is None
        assert deskabout.web_url("10.0.0.5") == "http://10.0.0.5/"
    finally:
        deskabout.lan_address = real
    assert "BETA" in deskboot.VERSION
    plain = deskboot.frame(xoxostyle.Theme(), version=None)
    assert deskboot.frame(xoxostyle.Theme()).tobytes() != plain.tobytes()   # the version drawn on the boot screen



def test_shutdown_screen(monkeypatch):
    """the touchscreen keeps its last picture once the Pi is off: a shutdown leaves the wait for SAFE TO UNPLUG
    and draws nothing over it (it showed "Shutting down" and looked stuck, 2026-11-07), the shutdown hook's
    picture written with the boot screen's; a refused power-off says so and the Studio carries on"""
    import bridge
    import deskboot
    import deskui
    import xoxostyle
    monkeypatch.setattr(bridge.time, "sleep", lambda s: None)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.desk = ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    asked = []
    monkeypatch.setattr(bridge, "run", lambda cmd, timeout=15, **k: (asked.append(cmd), (0, ""))[1])
    app.shutdown()
    assert asked == [["sudo", "-n", "systemctl", "poweroff"]]
    wait = deskboot.off_frame(ui.theme)                          # (no hook on this PC: the green light)
    assert wait.tobytes() == deskboot.off_frame(ui.theme, hook=False).tobytes()
    assert wait.tobytes() != deskboot.off_frame(ui.theme, hook=True).tobytes()
    assert app.display.image.tobytes() == wait.tobytes()
    app.render(force=True)                                       # the app's loop goes on until it's stopped
    assert app.display.image.tobytes() == wait.tobytes()
    assert wait.tobytes() != deskboot.off_frame(ui.theme, final=True).tobytes()
    monkeypatch.setattr(bridge, "run", lambda cmd, timeout=15, **k: (1, "sudo: a password is required\n"))
    app.shutdown()
    assert not app.powering_off and not app.busy
    assert app.message == "Can't shut down: sudo: a password is required"
    assert app.display.image.tobytes() != wait.tobytes()        # the screens back
    with tempfile.TemporaryDirectory() as tmp:
        splash = Path(tmp) / "splash.raw"
        assert deskboot.save(xoxostyle.Theme(), splash)
        unplug = splash.with_name("unplug.raw")
        assert unplug.read_bytes() == deskboot.rgb565(deskboot.off_frame(xoxostyle.Theme(), final=True))
        assert len(unplug.read_bytes()) == 480 * 320 * 2
        assert not deskboot.save(xoxostyle.Theme(), splash)      # unchanged: not written again
    hook = (Path(bridge.__file__).parent / "config" / "fm1-unplug").read_text()
    assert "@UNPLUG@" in hook and "fb_ili9486" in hook
    install = (Path(bridge.__file__).parent / "install.sh").read_text()
    assert "system-shutdown/fm1-unplug" in install and "unplug.raw" in install


def test_home_speaker_not_connected():
    """HOME's SPEAKER row: the last speaker's name alone looked connected when it wasn't (the second Studio's JBL,
    2026-11-07): "(OFF)" after it, CONNECTING... while it connects, its name once it is"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, last_mac="20:18:5B:EF:AA:B0", last_name="JBL Go 3"))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    speaker = lambda: next(r[2] for r in ui.home_rows() if r[0] == "spk")
    app.sink = None
    assert speaker() == "JBL GO 3 (OFF)"
    app.connecting = True
    assert speaker() == "CONNECTING..."
    app.connecting, app.sink = False, {"label": "JBL Go 3"}
    assert speaker() == "JBL GO 3"
    app.sink, app.state["last_name"] = None, None
    assert speaker() == "NONE"

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


def test_pocket_over_the_link():
    """a Pocket's sound over the link (RTP into fm1-pocket, ports receive_FL / receive_FR): a source, POCKET, with
    its ports; the Studio shows it only while a Pocket is on the network MIDI session"""
    import bridge
    node = {"id": 7, "type": "PipeWire:Interface:Node",
            "info": {"props": {"media.class": "Audio/Source", "node.name": "fm1-pocket"}}}
    ports = [{"type": "PipeWire:Interface:Port", "info": {"props": {"port.direction": "out", "port.name": f"receive_{c}",
                                                                      "node.id": 7, "port.id": k}}}
             for k, c in enumerate(("FL", "FR"))]
    _, sources = bridge.pick_nodes([node] + ports)
    assert [(n["label"], n["internal"], n["ports"]) for n in sources] == [("POCKET", True, ["receive_FL", "receive_FR"])]
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.midi = type("M", (), {"net": ["Kraken"]})()
    assert not app.pocket_linked()
    app.midi.net = ["Kraken", "FM-1 Companion Pocket"]
    assert app.pocket_linked()


def test_usb_host_is_the_port_configured(tmp_path):
    """a computer on the USB-C port: its controller "configured"; "not attached" (nothing plugged in, or a
    charger), no controller, or no /sys/class/udc (not a Pi 4): none"""
    import device
    (tmp_path / "fe980000.usb").mkdir()
    (tmp_path / "fe980000.usb" / "state").write_text("not attached")
    assert device.usb_host(tmp_path) is False
    (tmp_path / "fe980000.usb" / "state").write_text("configured")
    assert device.usb_host(tmp_path) is True
    assert device.usb_host(tmp_path / "none") is False


def test_speaker_battery():
    """a Bluetooth speaker that reports its battery: read from bluetoothctl info, on HOME's speaker row and in the
    web page's status; one that doesn't: nothing shown"""
    import bridge
    import deskui
    text = ("Device 20:18:5B:EF:AA:B0 (public)\n\tName: JBL Go 3\n\tConnected: yes\n"
            "\tBattery Percentage: 0x55 (85)")
    assert bridge.parse_info("20:18:5B:EF:AA:B0", text)["battery"] == 85
    assert "battery" not in bridge.parse_info("x", "\tName: JBL Go 3")
    was = bridge.bt
    bridge.bt = lambda *args, timeout=15: (0, text)
    try:
        assert bridge.speaker_battery("20:18:5B:EF:AA:B0") == 85 and bridge.speaker_battery(None) is None
    finally:
        bridge.bt = was
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.sink = {"id": 9, "name": "bluez_output.x", "label": "JBL Go 3"}
    ui = deskui.DeskUI(app, app.display)
    app.spk_battery = 85
    assert ui.home_rows()[-1][2] == "JBL GO 3  BAT 85%" and app.web_status()["speaker_battery"] == 85
    app.spk_battery = None
    assert ui.home_rows()[-1][2] == "JBL GO 3"


def test_mixer_mute_and_solo():
    """each mixer channel's M and S: muted, or silent while another is soloed, its fader level kept; one unplugged
    while soloed doesn't silence the rest; by touch, on HOME, and from the web page"""
    import bridge
    import deskui
    import web
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.others = [{"id": 1, "name": "alsa_input.usb-EP-136", "label": "EP-136"},
                  {"id": 4, "name": "alsa_input.usb-SMK", "label": "SMK-37+VA"}]
    ep, smk = [k for k, _ in app.mix_channels()]
    app.set_mix_level(smk, 150)
    assert (app.heard(ep), app.heard(smk)) == (100, 150)
    app.toggle_mute(ep)
    assert (app.heard(ep), app.heard(smk), app.mix_level(ep)) == (0, 150, 100)
    app.toggle_mute(ep)
    app.toggle_solo(smk)
    assert (app.heard(ep), app.heard(smk)) == (0, 150)
    app.toggle_mute(smk)                                               # soloed and muted: silent
    assert app.heard(smk) == 0
    app.toggle_mute(smk)
    app.others = app.others[:1]                                        # the soloed one unplugged
    assert app.heard(ep) == 100
    app.others = [{"id": 1, "name": "alsa_input.usb-EP-136", "label": "EP-136"},
                  {"id": 4, "name": "alsa_input.usb-SMK", "label": "SMK-37+VA"}]
    set_to = []                                                        # what reaches PipeWire
    real_run, bridge.run = bridge.run, lambda cmd, **kw: set_to.append(cmd)
    try:
        mixer = bridge.Mixer()
        mixer.set_levels([{"id": 7, "info": {"props": {"node.name": f"fm1-mix-{ep}"}}},
                          {"id": 8, "info": {"props": {"node.name": f"fm1-mix-{smk}"}}}],
                         {k: app.heard(k) for k in (ep, smk)})
    finally:
        bridge.run = real_run
    assert ["wpctl", "set-volume", "7", "0.00"] in set_to and ["wpctl", "set-volume", "8", "1.50"] in set_to
    app.toggle_solo(smk)

    ui = deskui.DeskUI(app, app.display)                               # by touch
    ui.theme_check = 1e12
    ui.open_tab("MIX")
    ui.render(0.0, force=True)

    def press(key):
        box = next(w[0] for w in ui.widgets if w[3] == key)
        ui.touch("down", box[0] + 3, box[1] + 3, 0.0)
        ui.touch("up", box[0] + 3, box[1] + 3, 0.0)
        ui.render(0.0, force=True)
    press(("m-mix", ep))
    press(("s-mix", smk))
    assert app.mutes == {ep} and app.solos == {smk}
    assert not any(w[3] in (("m-mix", "spk"), ("s-mix", "spk")) for w in ui.widgets)   # the speaker: no M / S
    texts = {row[0]: row[5] for row in ui.home_rows()}
    assert texts[ep] == "MUTE" and texts[smk] == "150%"
    app.toggle_mute(ep)
    assert {row[0]: row[5] for row in ui.home_rows()}[ep] == "OFF"     # silent under the other's SOLO

    app.web_command({"cmd": "set", "key": f"solo_{smk}", "value": False})   # from the web page
    app.web_command({"cmd": "set", "key": f"mute_{ep}", "value": True})
    app.web_command({"cmd": "set", "key": f"mute_{ep}", "value": True})    # (again: stays muted)
    rows = {r["key"]: r for r in app.web_status()["mixer"]}
    assert rows[ep]["mute"] is True and rows[smk]["solo"] is False and app.heard(smk) == 150
    assert web.check_command({"cmd": "set", "key": f"mute_{ep}", "value": True})["value"] is True
    for bad in ({"cmd": "set", "key": f"mute_{ep}", "value": 1}, {"cmd": "set", "key": "solo_spk", "value": True}):
        try:
            web.check_command(bad)
            assert False, bad
        except ValueError:
            pass


def test_pocket_fm1s_on_their_own():
    """a linked Pocket's FM-1s A-C, each on its own (seven-fm1s-design.md): their sound streams (fm1-pocket-a/b/c)
    are sources, named by a plug-in or POCKET FM-1 A; their network MIDI sessions are devices with a row and column
    of their own, sent to alone, and left out of NET; the Studio says it takes them, and gives a plug-in the
    Pocket's address"""
    import blemidi
    import bridge
    import netmidi
    import plugins
    conf = (Path(__file__).resolve().parent.parent / "fm1-bt-bridge" / "config" / "pipewire-fm1-pocket-in.conf").read_text()
    for port, x in ((46000, ""), (46002, "-a"), (46004, "-b"), (46006, "-c")):
        assert f"source.port = {port}" in conf and f'node.name = "fm1-pocket{x}"' in conf
    nodes = [{"id": 10 + i, "type": "PipeWire:Interface:Node",
              "info": {"props": {"media.class": "Audio/Source", "node.name": name, "node.description": desc}}}
             for i, (name, desc) in enumerate((("fm1-pocket", "Pocket (link)"), ("fm1-pocket-a", "Pocket FM-1 A"),
                                               ("fm1-pocket-b", "Pocket FM-1 B")))]
    _, sources = bridge.pick_nodes(nodes)
    assert [n["label"] for n in sources] == ["POCKET", "POCKET FM-1 A", "POCKET FM-1 B"]
    assert all(n["internal"] for n in sources)

    class Host:                                                         # the FM-1 Companion's rules, as a plug-in has them
        def source_label(self, props, counts):
            return {"fm1-pocket-a": "FM-1 E", "fm1-pocket-b": "FM-1 F"}.get(props.get("node.name"))
    _, sources = bridge.pick_nodes(nodes, Host())
    assert [n["label"] for n in sources] == ["POCKET", "FM-1 E", "FM-1 F"]

    sent = []                                                           # network MIDI: to one peer, or all but some

    class Sock:
        def sendto(self, packet, addr):
            sent.append(addr)
    s = netmidi.Session("XOXO Studio", 5004, lambda m, peer=None: None, by_peer=True)
    s.dsock = Sock()
    s.peers = {1: {"name": "FM-1 Companion Pocket", "data": ("10.0.0.2", 5005)},
               2: {"name": "FM-1 Companion Pocket FM-1 A", "data": ("10.0.0.2", 5007)},
               3: {"name": "Kraken", "data": ("10.0.0.9", 5005)}}
    s.send([bytes([0x90, 60, 100])], to="FM-1 Companion Pocket FM-1 A")
    assert sent == [("10.0.0.2", 5007)]
    sent.clear()
    s.send([bytes([0x90, 60, 100])], skip={"FM-1 Companion Pocket FM-1 A"})
    assert sorted(sent) == [("10.0.0.2", 5005), ("10.0.0.9", 5005)]
    got = []
    s.on_message = lambda m, peer=None: got.append(peer)
    s.received(netmidi.encode([bytes([0x90, 60, 100])], 1, 2), ("10.0.0.2", 5007), True)
    assert got == ["FM-1 Companion Pocket FM-1 A"]

    b = blemidi.MidiBridge(net=True)                                    # the MIDI process, the Studio's
    to_peer, to_dev = [], []
    b.net.names = lambda: ["FM-1 Companion Pocket", "FM-1 Companion Pocket FM-1 A", "FM-1 Companion Pocket FM-1 B"]
    b.net.send = lambda m, to=None, skip=(): to_peer.append((to, set(skip)))
    b.controllers.send_to = lambda name, m: to_dev.append(name)
    b.to_ble = lambda m: None
    assert b.device_names() == ["POCKET FM-1 A", "POCKET FM-1 B"]      # (no plug-in: the Pocket's letters)
    b.controllers.rules = [[r"Pocket FM-1 A$", "FM-1 E"], [r"Pocket FM-1 B$", "FM-1 F"]]
    assert b.device_names() == ["FM-1 E", "FM-1 F"] and b.controllers.names() == []
    assert "U:FM-1 E" in b.dests() and "NET" in b.dests()
    b.set_routes({"Box>U:FM-1 E": {"on": True}})
    b.deliver("BT>U:FM-1 E", [bytes([0x90, 60, 100])])
    assert to_peer == [("FM-1 Companion Pocket FM-1 A", set())] and to_dev == []
    to_peer.clear()
    b.deliver("BT>NET", [bytes([0x90, 60, 100])])                       # NET: not the FM-1s' own sessions
    assert to_peer == [(None, {"FM-1 Companion Pocket FM-1 A", "FM-1 Companion Pocket FM-1 B"})]
    to_peer.clear()
    b.set_routes({"U:FM-1 F>U:FM-1 E": {"on": True}})
    b.from_net(bytes([0x90, 62, 90]), "FM-1 Companion Pocket FM-1 B")   # FM-1 F played: to FM-1 E, by its route
    assert ("FM-1 Companion Pocket FM-1 A", set()) in to_peer and b.source_names["U:FM-1 F"] == "FM-1 F"

    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))               # status and the plug-ins' pocket()
    app.save_settings = lambda: None
    assert app.web_status()["pocket_fm1s"] is False and app.pocket_address() is None   # (Pocket sends: MIX)
    app.set_link_audio("fm1s")
    assert app.web_status()["pocket_fm1s"] is True and app.web_status()["link_audio"] == "fm1s"
    app.midi = type("M", (), {"net": ["FM-1 Companion Pocket"], "net_hosts": {"Kraken": "10.0.0.9",
                              "FM-1 Companion Pocket": "169.254.66.49"}})()
    assert app.pocket_address() == "169.254.66.49"
    host = plugins.Host(app)
    assert plugins.Studio(host, "x", {}).pocket() == "169.254.66.49"


def test_mixer_shows_only_the_pocket_fm1s_plugged_in():
    """the mixer's Pocket channels: none without a Pocket; POCKET while it sends one mix; once it sends its FM-1s
    apart, a channel for each FM-1 plugged into it (its own network MIDI session says so) and no POCKET"""
    import bridge
    nodes = [{"name": n, "label": n} for n in ("alsa_input.usb-EP-136", "fm1-pocket", "fm1-pocket-a",
                                               "fm1-pocket-b", "fm1-pocket-c")]
    names = lambda peers: [n["name"] for n in bridge.pocket_sources(nodes, peers)]   # noqa: E731
    assert names(["Kraken"]) == ["alsa_input.usb-EP-136"]
    assert names(["FM-1 Companion Pocket"]) == ["alsa_input.usb-EP-136", "fm1-pocket"]
    assert names(["FM-1 Companion Pocket", "FM-1 Companion Pocket FM-1 A", "FM-1 Companion Pocket FM-1 C"]) == [
        "alsa_input.usb-EP-136", "fm1-pocket-a", "fm1-pocket-c"]
    split = ["FM-1 Companion Pocket", "FM-1 Companion Pocket FM-1 A"]     # Pocket sends (the Studio's choice):
    mode = lambda m: [n["name"] for n in bridge.pocket_sources(nodes, split, m)]   # noqa: E731
    assert mode("mix") == ["alsa_input.usb-EP-136", "fm1-pocket"]          # MIX: POCKET alone, its FM-1s in it
    assert mode("midi") == ["alsa_input.usb-EP-136"]                       # MIDI ONLY: no Pocket channel


def test_plugin_detail_beside_a_source():
    """a plug-in's few words beside a source (the FM-1 Companion: an FM-1's firmware), on HOME and the web
    page's mixer, in place of USB; gone when it takes them away or is switched off"""
    import bridge
    import deskui
    import plugins
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.others = [{"id": 1, "name": "alsa_input.usb-Felucca", "label": "FM-1 A"},
                  {"id": 2, "name": "alsa_input.usb-EP-136", "label": "EP-136"}]
    studio = plugins.Studio(app.plugin_host, "fm1-companion", {})
    app.plugin_host.loaded["fm1-companion"] = studio
    ui = deskui.DeskUI(app, app.display)
    details = lambda: {label: detail for _, label, detail, _ in ui.sources()}   # noqa: E731
    assert details() == {"FM-1 A": "USB", "EP-136": "USB"}
    studio.set_detail("fm-1 a", "SLOOP 2.8")
    assert details() == {"FM-1 A": "SLOOP 2.8", "EP-136": "USB"}
    assert [r.get("detail") for r in app.web_status()["mixer"]] == ["SLOOP 2.8", None]
    ui.render(0.0, force=True)                                        # (HOME draws it)
    studio.set_detail("FM-1 A", None)
    assert details()["FM-1 A"] == "USB"
    studio.set_detail("FM-1 A", "FELUCCA 1.0.12 AND MORE")
    assert details()["FM-1 A"] == "FELUCCA 1.0.12 A"                  # (16 at most)
    app.plugin_host.loaded.clear()                                    # switched off
    assert details()["FM-1 A"] == "USB"


def test_receive_only_device_a_column_only():
    """the MIDI tab and the web page: a device that only receives (SYNTH A) is a column, not a row; one that only
    sends (nanoKEY2) a row, not a column; one both ways (EP-136) both"""
    import bridge

    class Midi:
        pads, xo4, net, mcu, clock, split = True, True, [], None, None, True
        controllers, receive_only, send_only = ["EP-136", "SYNTH A", "nanoKEY2"], ["SYNTH A"], ["nanoKEY2"]
        peer, enabled, error = None, True, None
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings, app.midi = (lambda: None), Midi()
    sources, dests = app.matrix_lists()
    assert "U:SYNTH A" in dests and "U:SYNTH A" not in sources and "U:EP-136" in sources
    assert "U:nanoKEY2" in sources and "U:nanoKEY2" not in dests and "U:EP-136" in dests
    assert "U:EP-136>U:SYNTH A" in app.routes() and not any(k.startswith("U:SYNTH A>") for k in app.routes())
    assert "U:nanoKEY2>U:SYNTH A" in app.routes() and not any(k.endswith(">U:nanoKEY2") for k in app.routes())
    web = app.web_status()["matrix"]
    assert "U:SYNTH A" in web["dests"] and "U:SYNTH A" not in web["sources"]



def test_dac_quiet(monkeypatch):
    """the DAC's analog stage set to -6 dB (its hiss in IEMs halved), by amixer on its card"""
    import bridge
    calls = []
    monkeypatch.setattr(bridge, "run", lambda cmd, **k: calls.append(cmd) or (0, ""))
    assert bridge.dac_quiet()
    assert calls == [["amixer", "-q", "-c", "BossDAC", "sset", "Analogue", "0"]]
    monkeypatch.setattr(bridge, "run", lambda cmd, **k: (1, "amixer: Invalid card number"))
    assert not bridge.dac_quiet()                                    # no DAC card: nothing else happens


def test_dac_is_the_master_out():
    """a DAC HAT: the master out (its headphone and RCA outs), whatever else is there; the Pi's jack the phones (a
    copy, CUE, the click); a Bluetooth speaker a copy; MASTER its level, on MIXER, HOME and the web page"""
    import bridge
    import deskui
    import web
    dac = {"id": 12, "name": "alsa_output.platform-soc_sound.stereo-fallback", "label": "DAC"}
    jack = {"id": 9, "name": "alsa_output.platform-bcm2835_audio.stereo-fallback", "label": "PHONES"}
    sink = {"id": 5, "name": "bluez_output.AA", "label": "JBL Go 3"}
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.dac, app.jack, app.sink = dac, jack, sink
    assert app.outputs() == (dac["name"], jack["name"]) and app.bt_copy() == sink["name"]   # "both"
    app.state["output"] = "speaker"
    assert app.outputs() == (dac["name"], None) and app.bt_copy() == sink["name"]
    app.state["output"] = "phones"
    assert app.outputs() == (dac["name"], jack["name"]) and app.bt_copy() is None
    app.state["output"], app.state["cue"] = "both", True
    assert app.cue_target() == jack["name"]                          # the click: the phones, not the master
    app.state["cue"] = False
    assert app.cue_target() == dac["name"]
    app.sink = None
    assert app.outputs() == (dac["name"], jack["name"]) and app.bt_copy() is None
    app.dac = None                                                   # no DAC: as before
    assert app.outputs() == (jack["name"], None)
    app.dac, app.sink = dac, sink

    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("MIX")
    ui.render(0.0, force=True)
    slider = next(w for w in ui.widgets if w[3] == ("slide", "master"))
    box = slider[0]
    ui.touch("down", (box[0] + box[2]) // 2, box[3] - 10, 0.0)        # dragged to the bottom: 0
    ui.touch("up", (box[0] + box[2]) // 2, box[3] - 10, 0.0)
    assert app.state["master"] == 0
    assert any(w[3] == ("slide", "spk") for w in ui.widgets) and any(w[3] == ("slide", "phones") for w in ui.widgets)
    rows = [r[0] for r in ui.home_rows()]
    assert rows[-2:] == ["master", "spk"]
    app.sink = None
    assert [r[0] for r in ui.home_rows()][-1] == "master"            # no speaker: no SPEAKER row
    ui.render(0.0, force=True)
    assert not any(w[3] == ("slide", "spk") for w in ui.widgets)

    app.web_command({"cmd": "set", "key": "master", "value": 64})       # the web page
    assert app.state["master"] == 64 and app.web_status()["master"] == 64
    assert web.check_command({"cmd": "set", "key": "master", "value": 64})["value"] == 64
    app.dac = None
    assert app.web_status()["master"] is None


def test_latency_steps_and_the_link_buffer():
    """MORE > AUDIO > Latency: PipeWire's block and the Pocket link's buffer lowered together, a step a press,
    round to SAFE; the installed receiver's buffer rewritten (and only when it changes)"""
    import bridge
    calls = []
    run, bridge.run = bridge.run, lambda cmd, **kw: (calls.append(cmd), (0, ""))[1]
    try:
        for name, quantum, ms in bridge.LATENCY:      # a Pocket's block and the Studio's: no resets
            assert ms > (max(quantum, bridge.POCKET_FLOOR) + quantum) * 1000 / 48000
        conf = Path(tempfile.mkdtemp()) / "pocket-in.conf"
        conf.write_text((Path(__file__).parent.parent / "fm1-bt-bridge" / "config"
                         / "pipewire-fm1-pocket-in.conf").read_text(encoding="utf-8"), encoding="utf-8")
        assert not bridge.set_link_buffer(44, conf) and not calls          # as shipped: nothing to do
        assert bridge.set_link_buffer(10, conf)
        text = conf.read_text(encoding="utf-8")
        assert text.count("sess.latency.msec = 10") == 5 and "msec = 44" not in text
        assert calls == [["systemctl", "--user", "restart", "fm1-pocket-in.service"]]
        assert bridge.set_link_buffer(18, conf, studio_ms=14)               # a following Studio's: its own
        text = conf.read_text(encoding="utf-8")
        assert text.count("sess.latency.msec = 18") == 4 and text.count("sess.latency.msec = 14") == 1
        assert "source.port = 46020\n      sess.latency.msec = 14" in text
        for name, quantum, _ in bridge.LATENCY:                # a following Studio's: a packet (or a block) and one
            packet = 1280 / 4 / 48                                    # of this Studio's blocks, no resets
            assert bridge.STUDIO_BUFFER[name] > max(packet, quantum / 48) + quantum / 48
        calls.clear()

        app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
        app.save_settings = lambda: None
        app.settings_menu = "audio"
        rows = {r[0]: r[2] for r in app.settings_rows()}
        assert rows["latency"] == "safe 44ms" and rows["link_return"] == "on" and rows["link_audio"] == "MIX"
        calls.clear()
        app.setting = [r[0] for r in app.settings_rows()].index("latency")
        app.change_setting()
        assert app.state["latency"] == "LOW" and bridge.AUDIO["quantum"] == 512
        assert ["pw-metadata", "-n", "settings", "0", "clock.force-quantum", "512"] in calls
        for _ in range(3):
            app.change_setting()
        assert app.state["latency"] == "SAFE" and bridge.AUDIO["quantum"] == 1024
        assert bridge.latency_step("nonsense")[0] == "SAFE"
        assert app.web_status()["latency"] == "SAFE"
        import web
        assert web.check_command({"cmd": "set", "key": "latency", "value": "LOWER"})
        try:
            web.check_command({"cmd": "set", "key": "latency", "value": "FAST"})
            assert False, "a step that isn't there"
        except ValueError:
            pass
        app.web_command({"cmd": "set", "key": "latency", "value": "LOWER"})     # the web page (and the tester)
        assert app.state["latency"] == "LOWER" and bridge.AUDIO["quantum"] == 256
        app.web_command({"cmd": "set", "key": "link_return", "value": False})
        assert app.state["link_return"] is False
        app.midi = type("Midi", (), {"follow_address": "10.0.0.1", "follows": "XOXO Studio"})()   # Follow Studio
        app.state["follow_studio"] = True
        posted = []
        app.post = lambda *event: posted.append(event)

        class Reply(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        opened, bridge.urllib.request.urlopen = bridge.urllib.request.urlopen, \
            lambda url, timeout: Reply(json.dumps({"latency": "LOWEST"}).encode())
        try:
            app.follow_latency()
            assert posted == [("latency_follow", "LOWEST")]   # (this one is LOWER)
            app.state["latency"] = "LOWEST"
            posted.clear()
            app.follow_latency()
            assert posted == []                                  # the same step already: nothing
        finally:
            bridge.urllib.request.urlopen = opened
    finally:
        bridge.run = run
        bridge.AUDIO["quantum"] = 1024


def test_usb_out():
    """no DAC HAT: the master copied to a USB interface's output, the first whose card has no MIDI (an interface,
    not a synth) at first; one picked by name, or none; MORE > AUDIO > USB out steps through them"""
    import bridge
    asound = Path(tempfile.mkdtemp(prefix="fm1-asound-"))
    for card, midi in ((1, False), (4, True)):
        (asound / f"card{card}").mkdir()
        if midi:
            (asound / f"card{card}" / "midi0").write_text("")

    def sink(i, name, card, card_name):
        return {"type": "PipeWire:Interface:Node", "id": i, "info": {"props": {
            "media.class": "Audio/Sink", "node.name": name, "alsa.card": card, "alsa.card_name": card_name}}}
    objects = [sink(64, "alsa_output.usb-Burr-Brown_from_TI_USB_Audio_CODEC-00.analog-stereo-output", 1,
                    "USB Audio CODEC"),
               sink(70, "alsa_output.usb-Some_Synth-00.analog-stereo", 4, "Some Synth"),
               sink(71, "alsa_output.usb-Companion_I_O-00.analog-stereo", 5, "Companion I/O"),
               sink(62, "alsa_output.platform-3f00b840.mailbox.stereo-fallback", 0, "bcm2835 Headphones")]
    outs = bridge.usb_out_nodes(objects, asound)
    assert [(o["label"], o["midi"]) for o in outs] == [("USB AUDIO CODEC", False), ("SOME SYNTH", True)]
    assert bridge.pick_usb_out(outs, "auto")["id"] == 64
    assert bridge.pick_usb_out(outs, outs[1]["name"])["id"] == 70 and bridge.pick_usb_out(outs, "off") is None
    assert bridge.pick_usb_out(outs, "alsa_output.usb-gone") is None
    assert bridge.pick_usb_out(outs[1:], "auto") is None              # a synth's output alone: not taken

    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.settings_menu = "audio"
    assert "usb_out" not in [r[0] for r in app.settings_rows()]       # none there: no row
    app.usb_outs, app.usb_out = outs, outs[0]
    app.jack = {"id": 62, "name": "alsa_output.platform-3f00b840.mailbox.stereo-fallback", "label": "PHONES"}
    rows = {r[0]: r[2] for r in app.settings_rows()}
    assert rows["usb_out"] == "AUTO: USB AUDIO CO"
    assert app.outputs() == (app.jack["name"], None)                  # the jack stays the master; USB gets a copy
    app.jack = None
    assert app.outputs()[0] == outs[0]["name"]                        # nothing else: the interface is it
    app.setting = [r[0] for r in app.settings_rows()].index("usb_out")
    app.change_setting()
    assert app.state["usb_out"] == outs[0]["name"]
    app.change_setting()
    app.change_setting()
    assert app.state["usb_out"] == "off"
    app.change_setting()
    assert app.state["usb_out"] == "auto"
    app.dac = {"id": 9, "name": "alsa_output.dac", "label": "DAC"}    # a DAC HAT: the master; no USB out row
    assert "usb_out" not in [r[0] for r in app.settings_rows()]

def test_the_mix_back_to_a_following_studio():
    """the leader sends a following Studio its mix less STUDIO (a mix-minus: it never hears itself late) on
    46012, Mix to Pocket on; the follower plays it on an output its link doesn't send from, or nowhere"""
    import bridge
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.midi = type("Midi", (), {"net_hosts": {"XOXO Studio Link on studio2": "169.254.40.59",
                                               "FM-1 Companion Pocket": "169.254.1.2"}})()
    assert app.studio_return_address() == "169.254.40.59"
    app.state["link_return"] = False
    assert app.studio_return_address() is None
    channels = [("u-felucca", {"name": "alsa_input.usb-Felucca", "label": "FELUCCA"}),
                ("u-studio", {"name": "xoxo-studio-in", "label": "STUDIO"}),
                ("u-xo4", {"name": "fm1-xo4", "label": "XO-4"})]
    app.app_here = set()
    assert [k for k, _, _ in app.studio_feeds(channels)] == ["u-felucca", "u-xo4"]
    text = bridge.receiver_config(bridge.STUDIO_RETURN_PORT, 12.92, bridge.LEADER_MIX, "x", "xoxo-leader-mix")
    assert "source.port = 46012" in text and "sess.latency.msec = 12.92" in text and '"xoxo-leader-mix"' in text
    jack = "alsa_output.platform-3f00b840.mailbox.stereo-fallback"
    usb = "alsa_output.usb-Burr-Brown_from_TI_USB_Audio_CODEC-00.analog-stereo-output"
    app.jack, app.usb_out = {"id": 62, "name": jack}, {"id": 140, "name": usb}
    assert app.leader_out(jack) == usb                                # the jack is the master: the interface
    app.usb_out = None
    assert app.leader_out(jack) is None                               # only the master itself: nowhere (round)
    assert app.leader_out("alsa_output.dac") == jack                  # a DAC the master: the jack

def test_a_studio_following():
    """Follow Studio: on the leader, a following Studio's mix (a port of its own, 46020) is a channel, STUDIO,
    beside a Pocket's; on the follower, its master goes to the leader's 46020 while linked"""
    import bridge
    nodes = [{"name": "fm1-pocket", "label": "POCKET"}, {"name": "xoxo-studio-in", "label": "STUDIO"},
             {"name": "alsa_input.usb-x", "label": "EP-136"}]
    label = lambda peers: [n["label"] for n in bridge.pocket_sources(nodes, peers, "mix")]   # noqa: E731
    assert label(["XOXO Studio Link on studio2"]) == ["STUDIO", "EP-136"]
    assert label(["FM-1 Companion Pocket"]) == ["POCKET", "EP-136"]
    assert label(["FM-1 Companion Pocket", "XOXO Studio Link on studio2"]) == ["POCKET", "STUDIO", "EP-136"]
    assert label([]) == ["EP-136"]
    conf = (Path(bridge.__file__).parent / "config" / "pipewire-fm1-pocket-in.conf").read_text()
    assert "source.port = 46020" in conf and 'node.name = "xoxo-studio-in"' in conf
    text = bridge.return_config("10.0.0.1", bridge.FOLLOW_PORT, bridge.FOLLOW_SINK, "Studio it follows (link)",
                                "xoxo-studio-link")
    assert 'destination.port = 46020' in text and 'node.name = "xoxo-studio-link"' in text
    assert "core.name = xoxo-studio-link" in text and 'node.name = "fm1-pocket-return"' in bridge.return_config("x")

    class Midi:
        net, follows, follow_address = [], None, None

        def __init__(self):
            self.follow = []

        def set_follow(self, on):
            self.follow.append(on)

        def set_clock(self, mode, bpm):
            self.clock = mode

    app = bridge.App(None, dict(bridge.DEFAULTS, clock_mode="box"))
    app.save_settings = lambda: None
    app.midi = Midi()
    assert app.follow_text() == "OFF" and app.follow_address() is None
    app.set_follow(True)
    assert app.midi.follow == [True] and app.state["clock_mode"] == "follow" and app.follow_text() == "LINKING"
    app.midi.follows, app.midi.follow_address = "XOXO Studio", "10.0.0.1"
    assert app.follow_text() == "ON" and app.follow_address() == "10.0.0.1"
    app.state["link_rec"] = True
    assert app.link_rec_peer() == "XOXO Studio"

def test_mix_back_to_the_pocket():
    """a linked Pocket gets the Studio's master back over the link (RTP to RETURN_PORT, its own format, 1-2 ms
    packets), Mix to Pocket on; off, or no Pocket: nothing sent"""
    import bridge
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    assert app.return_address() is None                               # no Pocket
    app.midi = type("M", (), {"net": ["FM-1 Companion Pocket"],
                              "net_hosts": {"FM-1 Companion Pocket": "169.254.10.20"}})()
    assert app.return_address() == "169.254.10.20"
    midi, app.midi = app.midi, None                                   # (the web status with no MIDI process)
    conf = bridge.return_config("169.254.10.20")
    for want in ('destination.ip = "169.254.10.20"', "destination.port = 46010", 'audio.format = "S16BE"',
                 "audio.rate = 48000", 'node.name = "fm1-pocket-return"'):
        assert want in conf
    assert "ptime" not in conf                                        # (1-2 ms packets overran: dirty)
    assert app.web_status()["link_return"] == bridge.RETURN_PORT
    app.settings_menu = "audio"
    app.setting = [r[0] for r in app.settings_rows()].index("link_return")
    app.change_setting()
    assert app.web_status()["link_return"] is None
    app.midi = midi
    assert app.return_address() is None


def test_linked_rec():
    """linked REC: REC here starts a take and sends MMC Record to the linked Pocket's own session (not its FM-1s');
    the Pocket's Record (MMC, from the network) starts one here, not sent back; Stop likewise; Linked REC off: none.
    A linked take notes where its first sample landed after its trigger"""
    import json
    import wave
    import blemidi
    import bridge
    import library
    import meters
    assert blemidi.mmc_command(bytes([0xF0, 0x7F, 0x7F, 0x06, 0x06, 0xF7])) == "record"
    assert blemidi.mmc_command(bytes([0xF0, 0x7F, 0x00, 0x06, 0x01, 0xF7])) == "stop"     # (any device id)
    assert blemidi.mmc_command(bytes([0x90, 60, 100])) is None
    b = blemidi.MidiBridge(net=False)
    routed = []
    b.route_from = lambda source, message: routed.append(message)
    b.from_net(blemidi.MMC["record"], "FM-1 Companion Pocket")
    assert b.mmc == [1, "record", "FM-1 Companion Pocket"] and routed == []        # the app's, not routed

    folder = Path(tempfile.mkdtemp())
    root, library.LIBRARY = library.LIBRARY, folder
    try:
        app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
        app.save_settings = lambda: None
        sent = []

        class Midi:
            net = ["Kraken", "FM-1 Companion Pocket", "FM-1 Companion Pocket FM-1 A"]

            def send_mmc(self, command, peer):
                sent.append((command, peer))
        app.midi = Midi()
        app.capture_target = lambda: "alsa_input.usb-Felucca"
        takes = []

        def start(target, path, rate=48000):
            takes.append(path)
            app.recorder.proc, app.recorder.path = type("P", (), {"poll": lambda self: None})(), path
            return True

        def stop():
            path, app.recorder.proc = app.recorder.path, None
            with wave.open(str(path), "wb") as w:                       # a second of sound
                w.setnchannels(2), w.setsampwidth(2), w.setframerate(48000)
                w.writeframes(bytes(4 * 48000))
            return path, 1.0
        app.recorder.start, app.recorder.stop = start, stop
        app.recorder.recording = lambda: app.recorder.proc is not None
        app.check_clipping = lambda *a: None

        app.toggle_recording()                                          # REC here
        assert app.recorder.recording() and sent == [("record", "FM-1 Companion Pocket")]
        app.link_rec("stop", "FM-1 Companion Pocket")                  # the Pocket's STOP
        assert not app.recorder.recording() and sent == [("record", "FM-1 Companion Pocket")]   # (not back)
        notes = json.loads(meters.link_file(takes[0]).read_text())
        assert notes["trigger"] == "here" and notes["linked_with"] == "FM-1 Companion Pocket"
        assert notes["seconds"] == 1.0 and isinstance(notes["first_sample_after_trigger_ms"], float)

        app.link_rec("record", "FM-1 Companion Pocket")                # the Pocket's REC
        assert app.recorder.recording() and len(sent) == 1
        app.link_rec("record", "FM-1 Companion Pocket")                # (already recording: nothing)
        assert app.recorder.recording() and len(takes) == 2
        app.toggle_recording()                                          # STOP here: the Pocket told
        assert not app.recorder.recording() and sent[-1] == ("stop", "FM-1 Companion Pocket")
        assert json.loads(meters.link_file(takes[1]).read_text())["trigger"] == "linked box"
        app.link_rec("record", "Kraken")                                # a DAW's MMC: not linked REC
        assert not app.recorder.recording()

        meters.link_file(takes[1]).unlink()                            # (takes a second apart share a name)
        app.state["link_rec"] = False                                   # Linked REC off
        app.link_rec("record", "FM-1 Companion Pocket")
        assert not app.recorder.recording()
        app.toggle_recording()
        assert app.recorder.recording() and len(sent) == 2               # (nothing sent)
        app.toggle_recording()
        assert not meters.link_file(takes[2]).exists()                  # (not a linked take: no notes)
        library.delete_recording(takes[0].name)
        assert not meters.link_file(takes[0]).exists()                  # (its notes go with it)
    finally:
        library.LIBRARY = root


def test_charging_bolt_by_the_battery():
    """the battery's percent with a green bolt beside it while it charges (PiSugar: external power plugged in), on
    HOME, the tabs' headers and RECORD; none on battery"""
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS))
    app.save_settings = lambda: None
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12

    def bolt(tab):
        ui.open_tab(tab)
        app.screen = "status"
        ui.render(0.0, force=True)
        img = app.display.image
        return any(img.getpixel((x, y)) == deskui.CHARGING for x in range(300, 480) for y in range(0, 30))
    app.battery = {"percent": 86, "mv": 3890, "plugged": True}
    assert bolt("HOME") and bolt("MIX") and bolt("MORE") and bolt("REC")
    app.battery = {"percent": 86, "mv": 3890, "plugged": False}
    assert not bolt("HOME") and not bolt("MIX")


def test_bluetooth_dongle_takes_over(monkeypatch, tmp_path):
    """a USB Bluetooth adapter (a dongle) takes over all of Bluetooth: the Pi's own powered off (through BlueZ), the
    dongle on, Bluetooth MIDI told; unplugged, the Pi's own again. A speaker not paired on the new one: said. If
    bluetoothctl's default isn't the one wanted (its commands would miss): said"""
    import bridge
    for name in ("hci0", "hci1"):
        (tmp_path / name).mkdir()
    real = {"hci0": "/sys/devices/platform/soc/3f215040.serial/serial0/serial0-0/bluetooth/hci0",
            "hci1": "/sys/devices/platform/soc/3f980000.usb/usb1/1-1/1-1.3/1-1.3:1.0/bluetooth/hci1"}
    monkeypatch.setattr(bridge.os.path, "realpath", lambda p: real[Path(p).parent.name] + "/device")
    address = {"hci0": "B8:27:EB:15:77:0A", "hci1": "E8:48:B8:C8:20:00"}
    present = {"hci0", "hci1"}
    calls = []
    default = {"is": None}                            # bluetoothctl's default controller (None: the one in use)
    blocked = set()                                   # adapters that won't power on (rfkill)

    def run(cmd, timeout=15, merge=True, clean=True):
        calls.append(cmd)
        if cmd[:2] == ["busctl", "set-property"] and cmd[3].rsplit("/", 1)[1] in blocked and cmd[-1] == "true":
            return 1, "Failed to set property Powered: org.bluez.Error.Blocked"
        if cmd[:2] == ["busctl", "get-property"]:
            hci = cmd[3].rsplit("/", 1)[1]
            return (0, f's "{address[hci]}"') if hci in present else (1, "unknown object")
        if cmd[:2] == ["bluetoothctl", "show"]:
            return 0, f"Controller {default['is'] or bridge.BT_IN_USE['address']} (public)"
        if cmd[0] == "bluetoothctl" and "info" in cmd:
            return 0, "\tName: JBL Go 3\n\tPaired: no"
        return 0, ""
    monkeypatch.setattr(bridge, "run", run)
    assert bridge.bt_adapters(str(tmp_path)) == [("E8:48:B8:C8:20:00", True, "hci1"),
                                                ("B8:27:EB:15:77:0A", False, "hci0")]
    present.discard("hci1")                           # (sysfs shows it before BlueZ has it: not listed yet)
    assert bridge.bt_adapters(str(tmp_path)) == [("B8:27:EB:15:77:0A", False, "hci0")]
    monkeypatch.setattr(bridge, "BT_IN_USE", {"address": None, "usb": False})
    monkeypatch.setattr(bridge, "bt_adapters", lambda: sorted(
        [(address[h], h == "hci1", h) for h in sorted(present)], key=lambda a: not a[1]))

    class Midi:
        moved = []

        def set_bt_adapter(self, a):
            self.moved.append(a)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, last_mac="20:18:5B:EF:AA:B0"))
    app.midi = Midi()
    said = []
    app.say = lambda text, seconds=3: said.append(text)
    app.bt_follow_dongle()                            # starts with the Pi's own: nothing said
    assert bridge.BT_IN_USE == {"address": "B8:27:EB:15:77:0A", "usb": False} and not said
    present.add("hci1")                               # a dongle that won't power on (blocked): the Pi's own kept
    blocked.add("hci1")
    calls.clear()
    app.bt_follow_dongle()
    app.bt_follow_dongle()                            # (tried again: said once)
    assert bridge.BT_IN_USE["address"] == "B8:27:EB:15:77:0A"
    assert not [c for c in calls if c[:2] == ["busctl", "set-property"] and c[-1] == "false"]
    assert said == ["Bluetooth dongle blocked: unplug it, or unblock it (rfkill)"]
    said.clear()
    blocked.clear()
    present.discard("hci1")
    present.add("hci1")                               # the dongle plugged in
    calls.clear()
    app.bt_follow_dongle()
    assert bridge.BT_IN_USE["address"] == "E8:48:B8:C8:20:00" and app.bt_usb
    assert app.midi.moved[-1] == "E8:48:B8:C8:20:00"
    power = [(c[3], c[-1]) for c in calls if c[:2] == ["busctl", "set-property"]]
    assert power == [("/org/bluez/hci1", "true"), ("/org/bluez/hci0", "false")]   # (the new one on first)
    assert said == ["Bluetooth dongle: pair the speaker again"]              # (the JBL was paired on the Pi's own)
    calls.clear()
    app.bt_follow_dongle()                            # nothing changed: nothing done
    assert not [c for c in calls if c[0] != "busctl"]
    present.discard("hci1")                           # unplugged: the Pi's own again
    default["is"] = "E8:48:B8:C8:20:00"               # ... but bluetoothctl still on the other: said
    app.bt_follow_dongle()
    assert bridge.BT_IN_USE == {"address": "B8:27:EB:15:77:0A", "usb": False} and not app.bt_usb
    assert said[-1] == "Bluetooth: couldn't move to the Pi's own"
    default["is"] = None                              # a speaker paired on the new one: connected at once
    present.add("hci1")
    monkeypatch.setattr(bridge, "run", lambda cmd, timeout=15, merge=True, clean=True: (
        run(cmd) if cmd[:2] != ["bluetoothctl", "info"] else (0, "	Paired: yes")))
    calls.clear()
    app.bt_follow_dongle()
    for _ in range(50):
        if ["bluetoothctl", "connect", "20:18:5B:EF:AA:B0"] in calls:
            break
        time.sleep(0.02)
    assert ["bluetoothctl", "connect", "20:18:5B:EF:AA:B0"] in calls and said[-1] == "Bluetooth: the USB dongle"


def test_bluetooth_devices_forget(monkeypatch):
    """MORE > STUDIO SETTINGS > BLUETOOTH DEVICES: what Bluetooth has paired or connected (a speaker, a saved
    keyboard, a phone on Bluetooth MIDI; not one a scan only saw), connected first; one forgotten held to confirm:
    the speaker unpaired and no longer the one reconnected to, a keyboard through the MIDI side"""
    import bridge
    import deskui
    infos = {"20:18:5B:EF:AA:B0": "\tAlias: JBL Go 3\n\tIcon: audio-card\n\tPaired: yes\n\tConnected: no\n"
                                  "\tUUID: Audio Sink                (0000110b-0000-1000-8000-00805f9b34fb)",
             "F0:5C:77:00:11:22": "\tAlias: KEY 25\n\tPaired: yes\n\tConnected: no",
             "28:9E:F6:01:02:03": "\tAlias: Pat's iPhone\n\tPaired: no\n\tConnected: yes",
             "AA:BB:CC:DD:EE:FF": "\tAlias: Somebody's TV\n\tPaired: no\n\tConnected: no"}
    calls = []

    def run(cmd, timeout=15, merge=True, clean=True):
        calls.append(cmd)
        if cmd[:2] == ["bluetoothctl", "devices"]:
            return 0, "".join(f"Device {mac} {info.split(chr(10))[0].split(': ')[1]}\n" for mac, info in infos.items())
        if cmd[:2] == ["bluetoothctl", "info"]:
            return 0, infos[cmd[2]]
        if cmd[:2] == ["bluetoothctl", "remove"]:
            return 0, "Device has been removed"
        return 0, ""
    monkeypatch.setattr(bridge, "run", run)
    known = bridge.bt_known([("F0:5C:77:00:11:22", "KEY 25"), ("C0:FF:EE:00:00:01", "Old keys")])
    assert [(d["name"], d["kind"], d["connected"]) for d in known] == [   # (one BlueZ forgot: still listed)
        ("Pat's iPhone", "other", True), ("JBL Go 3", "speaker", False), ("KEY 25", "keyboard", False),
        ("Old keys", "keyboard", False)]

    class Midi:
        enabled, pairing_until, controllers = True, 0.0, []
        ble_keys, forgot = [["F0:5C:77:00:11:22", "KEY 25", False]], []

        def ble_forget(self, address):
            self.forgot.append(address)
    app = bridge.App(RgbCapture(), dict(bridge.DEFAULTS, last_mac="20:18:5B:EF:AA:B0", last_name="JBL Go 3"))
    app.save_settings = lambda: None
    app.midi = Midi()
    app.job = lambda label, work: (lambda r: r[1] and app.say(r[1]))(work())   # (the job, at once)
    said = []
    app.say = lambda text, seconds=3: said.append(text)
    ui = deskui.DeskUI(app, app.display)
    ui.theme_check = 1e12
    ui.open_tab("SETTINGS")
    ui.render(0.0, force=True)
    keys = {w[3]: w for w in ui.widgets}

    def tap(key, hold=0.1):
        box = keys[key][0]
        ui.touch("down", box[0] + 2, box[1] + 2, 0.0)
        ui.touch("up", box[0] + 2, box[1] + 2, hold)
    tap(("more", "BLUETOOTH DEVICES"))
    assert app.screen == "pick" and app.pick["title"] == "BT devices"
    assert [i[:2] for i in app.pick["items"]] == [("Pat's iPhone", "phone etc, on"), ("JBL Go 3", "speaker"),
                                                 ("KEY 25", "keyboard")]
    app.pick["cursor"] = 1                            # the speaker: asked first, then forgotten
    app.on_key("press")
    assert app.screen == "confirm" and app.confirm["lines"][0] == "JBL Go 3"
    assert not [c for c in calls if c[:2] == ["bluetoothctl", "remove"]]
    app.on_key("press", True)
    assert ["bluetoothctl", "remove", "20:18:5B:EF:AA:B0"] in calls
    assert app.state["last_mac"] is None and not app.auto and said[-1] == "Forgot JBL Go 3"
    app.open_bt_devices()                             # a keyboard: through the MIDI side, not bluetoothctl
    app.pick["cursor"] = 2
    app.on_key("press")
    calls.clear()
    app.on_key("press", True)
    assert app.midi.forgot == ["F0:5C:77:00:11:22"] and not [c for c in calls if "remove" in c]
    infos.clear()                                     # nothing paired: said, no empty list
    app.midi.ble_keys = []
    app.screen = "settings"
    app.open_bt_devices()
    assert app.screen == "settings" and said[-1] == "No Bluetooth devices"


def test_speaker_scan_lists_only_heard(monkeypatch):
    """the speaker scan lists what was heard during it ([NEW], or a fresh RSSI), not every device BlueZ remembers:
    a paired JBL that's off was listed while the speaker being paired wasn't to be seen (2026-11-03)"""
    import bridge
    scan = ("Discovery started\n[CHG] Controller B8:27:EB:15:77:0A Discovering: yes\n"
            "[CHG] Device 7C:64:56:3F:84:6B RSSI: 0xffffffbf (-65)\n"
            "[CHG] Device 20:18:5B:EF:AA:B0 Connected: no\n"
            "[NEW] Device 11:FF:27:5A:21:89 AG-04\n")
    known = {"20:18:5B:EF:AA:B0": "JBL Go 3", "11:FF:27:5A:21:89": "AG-04", "7C:64:56:3F:84:6B": "[TV] Samsung"}

    def run(cmd, timeout=15, merge=True, clean=True):
        if "scan" in cmd:
            return 0, scan
        if cmd[:2] == ["bluetoothctl", "devices"]:
            return 0, "".join(f"Device {mac} {name}\n" for mac, name in known.items())
        if cmd[:2] == ["bluetoothctl", "info"]:
            return 0, f"\tName: {known[cmd[2]]}\n\tIcon: audio-card\n\tPaired: no"
        return 0, ""
    monkeypatch.setattr(bridge, "run", run)
    assert bridge.scan_seen(scan) == {"7C:64:56:3F:84:6B", "11:FF:27:5A:21:89"}
    assert [d["name"] for d in bridge.bt_scan(1)] == ["[TV] Samsung", "AG-04"]


def test_pairing_removes_and_scans_only_when_needed(monkeypatch):
    """pairing a speaker: removed first only if it's paired already (a stale pairing), scanned for only if BlueZ
    doesn't know it (an AG-04 that advertises now and then was removed, missed by the scan, "Not found" each time)"""
    import bridge
    state = {"info": "\tName: AG-04\n\tPaired: no"}
    calls = []

    def run(cmd, timeout=15, merge=True, clean=True):
        calls.append(cmd[1:3] if cmd[1] != "--timeout" else ["scan"])
        if cmd[:2] == ["bluetoothctl", "info"]:
            return 0, state["info"]
        if cmd[:2] == ["bluetoothctl", "remove"]:
            state["info"] = "Device 11:FF:27:5A:21:89 not available"
        if "pair" in cmd:
            return 0, "Pairing successful"
        if "connect" in cmd:
            return 0, "Connection successful"
        return 0, ""
    monkeypatch.setattr(bridge, "run", run)
    assert bridge.bt_pair("11:FF:27:5A:21:89")[0]
    assert ["remove", "11:FF:27:5A:21:89"] not in calls and ["scan"] not in calls     # known, not paired: at once
    calls.clear()
    state["info"] = "Device 11:FF:27:5A:21:89 not available"                           # forgotten since the scan
    bridge.bt_pair("11:FF:27:5A:21:89")
    assert ["scan"] in calls and ["remove", "11:FF:27:5A:21:89"] not in calls
    calls.clear()
    state["info"] = "\tName: AG-04\n\tPaired: yes"                                     # stale: removed, seen again
    bridge.bt_pair("11:FF:27:5A:21:89")
    assert calls.index(["remove", "11:FF:27:5A:21:89"]) < calls.index(["scan"])


def desk_with(off=(), tmp=None):
    """a Studio's screens, with the plug-ins in tmp (if any) found as in ~/xoxo-plugins and switched on, then some
    of them off (the sampler, the editor and the decks: XOXO-Studio-Plugins' tests)"""
    import bridge
    import copy
    import deskui
    app = bridge.App(RgbCapture(), copy.deepcopy(bridge.DEFAULTS))   # (its own plug-ins' settings, not the last test's)
    app.save_settings = lambda: None
    app.restart_app = lambda: None
    app.plugin_host.dirs = [Path(tmp)] if tmp else []
    import plugins
    app.state["plugins"] = {pid: {"on": True, "settings": {}} for pid in plugins.find(app.plugin_host.dirs)}   # (on)
    app.plugin_host.start()
    ui = deskui.DeskUI(app, app.display)
    app.desk = ui
    ui.theme_check = 1e12
    for pid in off:
        app.plugin_host.set_on(pid, False)
    return app, ui


def tab_keys(ui):
    ui.render(0.0, force=True)
    return [w[3][1] for w in ui.widgets if isinstance(w[3], tuple) and w[3][0] == "tab"]


def test_seq_eight_midi_tracks():
    """SEQ: eight MIDI tracks (channels 1-8), no pads on it; a step tapped takes the last notes and is selected,
    keys add notes (four at most) or take them off, VEL and LEN step, tapped again it's empty; CH steps a track's
    channel (held: back); LEN up to 64 (four pages); GRID puts a note on a step or off; HOLD CLR empties it"""
    app, ui = desk_with()
    sent = []

    class Seq:
        step = pattern = queued = None

        def send(self, *msg):
            sent.append(msg)
    app.sequencer = Seq()
    ui.open_tab("SEQ")
    ui.render(0.0, force=True)
    keys = {w[3] for w in ui.widgets}
    assert {("seq-track", k) for k in range(8)} <= keys and ui.tab_label("SEQ") == "SEQ"
    assert not any("pad" in str(k) or "xo4" in str(k) or "rec" in str(k) for k in keys)
    assert [t["channel"] for t in app.song()["tracks"]] == list(range(8))

    def steps(k=0):
        return app.song()["patterns"]["A"][k]["steps"]
    ui.sq_tap(0)
    assert steps()[0]["notes"] == [60] and ui.sq_step == 0 and sent[-1][0] == "song"
    ui.sq_key(64)
    ui.sq_key(67)
    assert steps()[0]["notes"] == [60, 64, 67]
    ui.sq_key(64)
    assert steps()[0]["notes"] == [60, 67]
    ui.sq_change("vel", -8)
    ui.sq_change("len", 0.5)
    assert steps()[0]["vel"] == 92 and steps()[0]["len"] == 1.5
    ui.sq_tap(4)                                                     # an empty step: the last notes
    assert steps()[4]["notes"] == [60, 67] and ui.sq_step == 4
    ui.sq_tap(4)                                                     # the selected one again: empty
    assert steps()[4] is None and ui.sq_step is None
    ui.sq_pick_track(2)                                              # track 3: MIDI channel 3
    ui.sq_channel(1)
    assert app.song()["tracks"][2]["channel"] == 3
    ui.sq_channel(-1)
    assert app.song()["tracks"][2]["channel"] == 2
    for _ in range(48):                                              # LEN to 64: four pages
        ui.sq_length(1)
    ui.render(0.0, force=True)
    assert app.song()["patterns"]["A"][2]["len"] == 64
    assert {("seq-page", pg) for pg in range(4)} <= {w[3] for w in ui.widgets}
    ui.sq_go_page(3)
    ui.sq_tap(63)
    assert steps(2)[63]["notes"] == [60]
    ui.sq_toggle_grid()
    ui.render(0.0, force=True)
    cells = [w[3] for w in ui.widgets if isinstance(w[3], tuple) and w[3][0] == "seq-cell"]
    assert len(cells) == 16 * 8 and {c[1] for c in cells} == set(range(48, 64))
    ui.sq_grid_tap(50, 62)
    assert steps(2)[50]["notes"] == [62]
    ui.sq_grid_tap(50, 62)
    assert steps(2)[50] is None
    ui.sq_clear()
    assert not any(steps(2))


def test_studio_without_its_plugins():
    """the Studio with none of the plug-ins (no sampler, editor or decks): HOME, MIXER, MIDI, RECORD, SEQ and MORE;
    their tabs can't be opened, no PADS or DECKS channel, no DECKS setting, no MIDI controllers kept off the routes;
    every screen draws"""
    import copy
    import bridge
    import deskui
    app = bridge.App(RgbCapture(), copy.deepcopy(bridge.DEFAULTS))
    app.save_settings = lambda: None
    app.plugin_host.dirs = [Path(tempfile.mkdtemp(prefix="xoxo-noplugins-"))]
    app.plugin_host.start()
    ui = deskui.DeskUI(app, app.display)
    app.desk = ui
    ui.theme_check = 1e12
    assert tab_keys(ui) == ["HOME", "MIX", "MIDI", "REC", "SEQ", "MORE"] and ui.tab_label("SEQ") == "SEQ"
    assert not any(app.plugin_on(pid) for pid in ("editor", "decks"))
    assert ui.editor_screen() is None and ui.app_sounds() == []
    for name in ("EDITOR", "DECKS"):
        ui.open_tab(name)
        assert ui.tab == "HOME"
    app.screen = "editor"                                            # (nothing to draw it with: the tab instead)
    ui.render(0.0, force=True)
    app.screen = "status"
    for tab in ("HOME", "MIX", "MIDI", "REC", "SEQ", "MORE", "PLUGINS"):
        ui.open_tab(tab)
        ui.render(0.0, force=True)
        assert ui.tab == tab, tab
    assert not app.edit_action()
    for name in ("PADS", "EDITOR", "DECKS"):
        ui.open_tab(name)
        assert ui.tab == "HOME"
    app.screen, app.settings_menu = "settings", "audio"
    assert "DJ decks out" not in [r[1] for r in app.settings_rows()]
    app.screen = "status"
    assert app.plugin_host.taken_controllers() == [] and app.app_nodes() == {}
    st = app.web_status()
    assert st["decks"] is None and st["kits"] is None
    assert st["plugins"]["builtin"] == {"editor": False, "decks": False, "sampler": False}
    objects = [{"id": 7, "type": "PipeWire:Interface:Node", "info": {"props": {
        "media.class": "Audio/Source", "node.name": "fm1-xo4", "node.description": "XO-4"}}}]
    assert bridge.pick_nodes(objects, app.plugin_host)[1] == []    # (the pads' channel: the sampler's)


def test_old_settings_move_to_the_sequencer(tmp_path, monkeypatch):
    """a Studio's settings from when the sequencer was XO-4's: its song and the routes from XO4 (and in the route
    presets) are the sequencer's (SEQ) now; the pads' kit, note repeat and MIDI IN move to the sampler plug-in's
    settings, the decks' output to the decks plug-in's"""
    import bridge
    song = {"pattern": "C"}
    old = {"xo4": song, "xo4_midi_in": True, "decks_out": "hercules", "kit": {"name": "MINE"}, "repeat": 2,
           "routes": {"XO4>USB": {"on": True}, "BT>SMP": {"on": False}},
           "route_presets": {"1": {"routes": {"XO4>NET": {"on": True}}, "saved": 1}}}
    path = tmp_path / "fm1-bridge.json"
    path.write_text(json.dumps(old))
    monkeypatch.setattr(bridge, "STATE_FILE", path)
    state = bridge.load_state()
    assert state["seq"] == song and "xo4" not in state and "xo4_midi_in" not in state and "kit" not in state
    assert state["plugins"]["sampler"]["settings"] == {"kit": {"name": "MINE"}, "repeat": 2, "midi_in": True}
    assert state["routes"] == {"SEQ>USB": {"on": True}, "BT>SMP": {"on": False}}
    assert state["route_presets"]["1"]["routes"] == {"SEQ>NET": {"on": True}}
    assert state["plugins"]["decks"]["settings"]["out"] == "hercules" and "decks_out" not in state
