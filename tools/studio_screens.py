"""Render XOXO Studio's touch screens to PNG files for the README, with the Studio's own drawing code (deskui.py and
its pages) and a made-up studio: the 808 KIT, a pattern in XO-4, a USB keyboard, both decks loaded, a speaker that
reports its battery. No Pi, no screen, no sound: the processes are stand-ins that only answer what the screens ask.

  python tools/studio_screens.py OUTDIR [--scale 2]

Each picture is the 480x320 screen, scaled up with square pixels (2x by default).
"""
import argparse
import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="xoxo-shots-"))     # an empty library: the same pictures on any computer
os.environ.update(FM1_LIBRARY=str(TMP / "library"), XDG_RUNTIME_DIR=str(TMP / "run"), FM1_SD_LIBRARY=str(TMP / "sd"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fm1-bt-bridge"))

from PIL import Image  # noqa: E402

import bridge  # noqa: E402
import deskabout  # noqa: E402
import deskui  # noqa: E402
import library  # noqa: E402
import pads  # noqa: E402
import xo4  # noqa: E402

DRUMS = ("KICK", "KICK-2", "SNARE", "CLAP", "HAT", "OPEN-HAT", "PEDAL-HAT", "RIM", "SNARE-2", "LOW-TOM", "HI-TOM",
         "CRASH", "RIDE", "SHAKER", "CONGA", "COWBELL")


class Capture:
    image = theme = None

    def show_rgb(self, img):
        self.image = img.copy()


class Pads:
    """the pad process, as far as the screens ask"""
    sounding, step = [4], None

    def send(self, *msg):
        pass


class XO4:
    """the XO-4 process: playing pattern A, step 5"""
    step, pattern, queued = 4, "A", None

    def send(self, *msg):
        pass


class Midi:
    """the MIDI process: two USB devices, the pads, XO-4, the box's clock at 120"""
    enabled, error, peer, pairing_until, split, pads, xo4 = True, None, None, 0.0, True, True, True
    controllers, net, mcu, notes, chans, ble_keys = ["EP-136", "KeyStep 37"], [], None, [], 0, []
    clock = {"bpm": 120, "tempo": 120.0, "source": "box", "playing": True, "bar": 0.0}

    def activity(self):
        return 0.0

    def set_routes(self, routes):
        pass

    def set_clock(self, *args):
        pass


class Decks:
    """the decks program: two tracks loaded, A playing with ECHO on"""
    library = [["a.mp3", "Night Drive", "XOXO", 124.0, "Am", "8A"], ["b.mp3", "Pocket Studio", "XOXO", 122.0, "Cm", "5A"],
               ["c.mp3", "Groove Box", "XOXO", 126.0, "Fm", "4A"]]
    overviews = {0: [abs(math.sin(i / 9)) * 0.8 + 0.1 for i in range(220)],
                 1: [abs(math.sin(i / 13 + 1)) * 0.7 + 0.15 for i in range(220)]}
    note, library_n, note_n = None, 0, 0
    status = {"decks": [{"title": "Night Drive", "artist": "XOXO", "bpm": 124.0, "key": "Am", "camelot": "8A",
                         "pos": 92.0, "len": 300.0, "playing": True, "pitch": 0.0, "synced": True, "cues": [],
                         "fx": "ECHO", "fx_on": True},
                        {"title": "Pocket Studio", "artist": "XOXO", "bpm": 124.0, "key": "Cm", "camelot": "5A",
                         "pos": 41.0, "len": 260.0, "playing": False, "pitch": 1.6, "synced": True, "cues": [],
                         "fx": "REVERB", "fx_on": False}],
              "xfade": 0.35, "cursor": 1, "scanning": None, "source": "STUDIO", "sources": 1}

    def running(self):
        return True

    def send(self, *cmd):
        pass


def take(path, seconds=3.0, rate=48000):
    """a made-up recording: a decaying chord, so the editor has a waveform to show"""
    n = int(seconds * rate)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        v = sum(math.sin(2 * math.pi * f * t) for f in (220, 277, 330)) / 3 * math.exp(-1.2 * (t % 1.0)) * 0.6
        s = int(v * 32767)
        frames += struct.pack("<hh", s, s)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def studio():
    """the made-up studio: the app and its screens"""
    kit = pads.empty_kit("808 KIT")
    for i, name in enumerate(DRUMS):
        kit["pads"][i]["sample"] = f"/samples/808-{name}.wav"
    song = xo4.empty_song()
    drums = song["patterns"]["A"][xo4.DRUMS]["steps"]
    for i in range(16):
        hits = ([0] if i % 4 == 0 else []) + ([2] if i in (4, 12) else []) + ([4] if i % 2 == 0 else [])
        if hits:
            drums[i] = {"notes": hits, "levels": [3 if (h == 0 and i == 0) else 1 if h == 4 and i % 4 else 0
                                                  for h in hits], "ratchets": [2 if i == 14 else 1] * len(hits)}
    drums[14] = {"notes": [4], "levels": [0], "ratchets": [3]}
    keys = song["patterns"]["A"][xo4.SYNTH1]["steps"]
    keys[0] = {"notes": [60, 64, 67, 71], "vel": 90, "len": 6}
    keys[8] = {"notes": [57, 60, 64, 67], "vel": 90, "len": 6}
    bass = song["patterns"]["A"][xo4.SYNTH2]
    bass["len"] = 12
    for i, note in ((0, 36), (3, 36), (6, 43), (9, 41)):
        bass["steps"][i] = {"notes": [note], "vel": 110}
    state = dict(bridge.DEFAULTS, kit=kit, xo4=xo4.clean_song(song), mix={"u-xo4": 90, "u-sampler": 110,
                                                                           "u-ep136": 70, "decks": 120},
                 repeat=2, last_name="JBL Go 3", bpm=120, clock_mode="box")
    display = Capture()
    app = bridge.App(display, state)
    app.save_settings = lambda: None
    app.midi, app.pads, app.xo4 = Midi(), Pads(), XO4()
    app.playing = True
    app.battery = {"percent": 78, "mv": 3800, "plugged": False}
    app.sink, app.volume, app.spk_battery = {"id": 9, "name": "bluez_output.jbl", "label": "JBL Go 3"}, 64, 80
    app.others = [{"id": 1, "name": "fm1-xo4", "label": "XO-4", "internal": True},
                  {"id": 2, "name": "fm1-sampler", "label": "SAMPLER", "internal": True},
                  {"id": 3, "name": "alsa_input.usb-casio", "label": "EP-136"}]
    ui = deskui.DeskUI(app, display)
    ui.theme_check = 1e12
    ui.decks_proc = Decks()
    return app, ui


def shot(app, ui, out, name, scale, setup):
    setup(app, ui)
    ui.render(0.0, force=True)
    img = app.display.image
    img.resize((img.width * scale, img.height * scale), Image.NEAREST).save(out / f"{name}.png")
    print("wrote", out / f"{name}.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    take(library.folder("recordings") / "2026-10-28_143000_take.wav")

    def xo4_tab(track, **attrs):
        def setup(app, ui):
            ui.open_tab("XO4")
            ui.xo4_track = track
            for k, v in attrs.items():
                setattr(ui, k, v)
        return setup

    def editor(app, ui):
        ui.open_tab("EDITOR")
        app.open_editor("2026-10-28_143000_take.wav", "recordings")
        ui.ed_files = False
        import time
        for _ in range(100):                     # the take loads in the background
            if app.ed and not app.ed.get("loading"):
                break
            time.sleep(0.05)

    scenes = [
        ("studio-home", lambda app, ui: ui.open_tab("HOME")),
        ("studio-mixer", lambda app, ui: ui.open_tab("MIX")),
        ("studio-xo4-drums", xo4_tab(0, xo4_step=4, xo4_pad=0)),
        ("studio-xo4-synth", xo4_tab(1, xo4_step=0)),
        ("studio-xo4-grid", xo4_tab(0, xo4_grid=True, xo4_step=4, xo4_pad=0)),
        ("studio-xo4-grid-synth", xo4_tab(2, xo4_grid=True, xo4_step=0)),
        ("studio-xo4-sound", xo4_tab(1, xo4_sound=True)),
        ("studio-xo4-pads", xo4_tab(0, mpc_open=True)),
        ("studio-xo4-fx", xo4_tab(1, fx_open=True, fx_dest="xo4", xo4_fx=[14, True])),
        ("studio-decks", lambda app, ui: setattr(ui, "tab", "DECKS")),
        ("studio-editor", editor),
        ("studio-midi", lambda app, ui: ui.open_tab("MIDI")),
        ("studio-more", lambda app, ui: ui.open_tab("MORE")),
        ("studio-settings", lambda app, ui: ui.open_tab("SETTINGS")),
        ("studio-about", lambda app, ui: ui.open_tab("ABOUT")),
    ]
    deskabout.lan_address = lambda: "192.168.1.20"    # (a made-up address, not this computer's)
    app, ui = studio()
    for name, setup in scenes:
        if app.screen == "editor":               # (the editor leaves the screen to the next scene)
            app.editor_close()
            app.screen = "status"
        shot(app, ui, args.out, name, args.scale, setup)


if __name__ == "__main__":
    main()
