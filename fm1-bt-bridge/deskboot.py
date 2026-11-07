"""The Studio's boot screen (480x320), in the XOXO look and the last theme it showed: XOXO // STUDIO and its version, a line along
the start-up's steps until HOME takes over, and XOXO//AUDIO//LABS.

Two moments use it. Early in boot, before the app runs, a udev rule copies splash.raw onto the screen as soon as
the touchscreen's framebuffer appears (install.sh; the kernel's console is kept off the screen), so the boot text
never shows. Then the app draws the steps over it (main(): show() after each one). save() writes splash.raw from
the theme in use, so the next boot's first picture matches.

Shutting down uses it too (off_frame). The touchscreen keeps its last picture once the Pi is off (its light runs
from the 5 V pin), so the app leaves "SHUTTING DOWN" with a wait, and at the very end of the power-off, after
everything else has stopped, systemd's shutdown hook (config/fm1-unplug, from install.sh) copies unplug.raw onto
the screen: SAFE TO UNPLUG."""

from pathlib import Path

from PIL import Image, ImageDraw

import xoxostyle as st

W, H = 480, 320
STEPS = ("STARTING THE SAMPLER", "STARTING MIDI", "STARTING AUDIO", "FINDING YOUR DEVICES")
VERSION = "0.2.2 BETA"
SPLASH = Path.home() / ".local" / "share" / "fm1-bridge" / "splash.raw"   # RGB565, what udev copies at boot
UNPLUG = SPLASH.with_name("unplug.raw")             # RGB565, what the shutdown hook copies at the very end
HOOK = Path("/usr/lib/systemd/system-shutdown/fm1-unplug")   # the shutdown hook (install.sh): root's to put there


def theme(state):
    """the theme the Studio last showed (state "boot_theme", saved by the desk UI), else the picked one"""
    saved = state.get("boot_theme")
    if saved and saved.get("name") in st.ALL:      # (one saved before the XOXO look: the picked one instead)
        return st.theme_load(saved)
    pick = state.get("desk_theme")
    return st.Theme(pick) if pick in st.ALL else st.Theme()


def mark(img, y, parts, size, colour, slashes):
    """parts in a row, centred, the "//" between them in the slashes' colour"""
    gap = 8 if size > 1 else 0
    x = (W - sum(st.text_size(p, size)[0] for p in parts) - gap * (len(parts) - 1)) // 2
    for p in parts:
        st.text(img, (x, y), p, slashes if p == "//" else colour, size)
        x += st.text_size(p, size)[0] + gap


def frame(t, step=None, version=VERSION):
    """the boot screen; step: the index into STEPS under way (None: the picture before the app runs)"""
    img = Image.new("RGB", (W, H), t.bg)
    d = ImageDraw.Draw(img)
    mark(img, 96, ("XOXO", "//", "STUDIO"), 3, t.hi, t.c[2])
    if version:                                     # the release, under the name
        st.text(img, ((W - st.text_size(version)[0]) // 2, 152), version, t.c[3])
    left, right, y = 120, W - 120, 196              # the start-up's line: the steps done in the highlight
    d.rectangle((left, y, right, y + 3), fill=t.c[0])
    done = 0 if step is None else step + 1
    d.rectangle((left, y, left + (right - left) * done // len(STEPS), y + 3), fill=t.hi)
    label = "STARTING..." if step is None else STEPS[step]
    st.text(img, ((W - st.text_size(label)[0]) // 2, y + 14), label, t.c[2])
    mark(img, H - 30, ("XOXO", "//", "AUDIO", "//", "LABS"), 1, t.hi, t.c[2])
    d.rectangle((W - 14, H - 14, W - 8, H - 8), fill=t.track[0])       # the signal dot
    return img


def off_frame(t, final=False, hook=None):
    """the picture a shutdown leaves: final (the hook's, the Pi off): SAFE TO UNPLUG; else the wait for it, or
    (no hook here yet: install.sh not run since it came) for the Pi's green light to go out"""
    if hook is None:
        hook = HOOK.exists()
    img = Image.new("RGB", (W, H), t.bg)
    mark(img, 96, ("XOXO", "//", "STUDIO"), 3, t.hi, t.c[2])
    wait = "WAIT FOR SAFE TO UNPLUG" if hook else "UNPLUG WHEN THE GREEN LIGHT GOES OUT"
    lines = (("SAFE TO UNPLUG", t.hi),) if final else (("SHUTTING DOWN...", t.hi), (wait, t.c[2]))
    for i, (text, colour) in enumerate(lines):
        st.text(img, ((W - st.text_size(text)[0]) // 2, 170 + 24 * i), text, colour)
    mark(img, H - 30, ("XOXO", "//", "AUDIO", "//", "LABS"), 1, t.hi, t.c[2])
    return img


def show(display, t, step=None):
    display.show_rgb(frame(t, step))


def rgb565(img):
    import numpy as np
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    return (((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)).astype("<u2").tobytes()


def save(t, path=SPLASH):
    """splash.raw for the next boot's first picture, and unplug.raw for a shutdown's last, in this theme (each
    only written when it changes); True when the boot's changed"""
    wrote = False
    for where, img in ((path, frame(t)), (path.with_name(UNPLUG.name), off_frame(t, final=True))):
        data = rgb565(img)
        try:
            if where.exists() and where.read_bytes() == data:
                continue
            where.parent.mkdir(parents=True, exist_ok=True)
            where.write_bytes(data)
            wrote = wrote or where == path
        except OSError:
            pass
    return wrote
