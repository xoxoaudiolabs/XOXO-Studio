"""The Studio's boot screen (480x320), in the XOXO look and the last theme it showed: XOXO // STUDIO, a line along
the start-up's steps until HOME takes over, and XOXO//AUDIO//LABS.

Two moments use it. Early in boot, before the app runs, a udev rule copies splash.raw onto the screen as soon as
the touchscreen's framebuffer appears (install.sh; the kernel's console is kept off the screen), so the boot text
never shows. Then the app draws the steps over it (main(): show() after each one). save() writes splash.raw from
the theme in use, so the next boot's first picture matches."""

from pathlib import Path

from PIL import Image, ImageDraw

import xoxostyle as st

W, H = 480, 320
STEPS = ("STARTING THE SAMPLER", "STARTING MIDI", "STARTING AUDIO", "FINDING YOUR DEVICES")
VERSION = "0.1"
SPLASH = Path.home() / ".local" / "share" / "fm1-bridge" / "splash.raw"   # RGB565, what udev copies at boot


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
    left, right, y = 120, W - 120, 196              # the start-up's line: the steps done in the highlight
    d.rectangle((left, y, right, y + 3), fill=t.c[0])
    done = 0 if step is None else step + 1
    d.rectangle((left, y, left + (right - left) * done // len(STEPS), y + 3), fill=t.hi)
    label = "STARTING..." if step is None else STEPS[step]
    st.text(img, ((W - st.text_size(label)[0]) // 2, y + 14), label, t.c[2])
    mark(img, H - 30, ("XOXO", "//", "AUDIO", "//", "LABS"), 1, t.hi, t.c[2])
    d.rectangle((W - 14, H - 14, W - 8, H - 8), fill=t.track[0])       # the signal dot
    if version:
        st.text(img, (8, H - 22), version, t.c[1])
    return img


def show(display, t, step=None):
    display.show_rgb(frame(t, step))


def rgb565(img):
    import numpy as np
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    return (((a[..., 0] >> 3) << 11) | ((a[..., 1] >> 2) << 5) | (a[..., 2] >> 3)).astype("<u2").tobytes()


def save(t, path=SPLASH):
    """splash.raw for the next boot's first picture, in this theme (only written when it changes)"""
    data = rgb565(frame(t))
    try:
        if path.exists() and path.read_bytes() == data:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True
    except OSError:
        return False
