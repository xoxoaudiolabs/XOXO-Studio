"""Which build of the box this is, and what it can do.

Two builds share one codebase: the pocket box (a Pi Zero W with the Waveshare 1.3" OLED HAT, joystick and
three keys) and the desk box (a Pi 3/4 with a 3.5" 480x320 SPI touchscreen). The box looks at its board and
screen at start; features that need more than a Zero can carry ask detect()'s "can" set instead of the board.
Settings' "build" ("auto", "pocket" or "desk") overrides the guess.
"""

import os
from pathlib import Path

MODEL = Path("/proc/device-tree/model")
FRAMEBUFFERS = Path("/sys/class/graphics")
UDC = Path("/sys/class/udc")               # a Pi 4's USB-C port as a USB device (xoxo-usb-gadget.sh): its controller


def usb_host(path=UDC):
    """a computer on the USB-C port, using the Studio as its USB interface: the port's controller "configured"
    (the computer has taken the gadget). The gadget's sound card and MIDI port are there from start with nothing
    plugged in (the controller "not attached"), so their being there doesn't mean a computer is"""
    try:
        return any((p / "state").read_text().strip() == "configured" for p in path.iterdir())
    except OSError:
        return False


def board(path=MODEL):
    """"Raspberry Pi 3 Model B Plus Rev 1.3", or "" off a Pi"""
    try:
        return path.read_bytes().rstrip(b"\0").decode(errors="replace")
    except OSError:
        return ""


def fast(model):
    """a Pi 4 / 400 / 5 or a Compute Module 4 / 5: about twice a Pi 3's speed a core (measured 2026-11-07: a Pi 4
    ran four of the Studio's sound at full load at once, every engine at its cap, before its blocks came late)"""
    return model.startswith(("Raspberry Pi 4", "Raspberry Pi 400", "Raspberry Pi 5",
                             "Raspberry Pi Compute Module 4", "Raspberry Pi Compute Module 5"))


def hdmi35(width, height):
    """the 3.5" HDMI touchscreen's framebuffer: HDMI set to a whole multiple of its 480x320 panel, or 1.5x
    (install.sh --screen hdmi: the screen shows no signal at 480x320 itself, and scales what it gets down to its
    panel). From FM-1 Companion (its Studio's), 2026-10-29"""
    return (width, height) in ((720, 480), (960, 640), (1440, 960))


def touchscreen(root=FRAMEBUFFERS):
    """(framebuffer device, width, height) of a small SPI screen (480x320), or None: fbtft's (fb_ili9486) or the
    kernel's DRM driver's (ili9486drmfb: the piscreen overlay's, Raspberry Pi OS from 2026), which is /dev/fb0
    when no HDMI monitor was there at boot, else /dev/fb1. Else the 3.5" HDMI touchscreen's (hdmi35): an SPI
    screen first, so an HDMI monitor that happens to run at 720x480 beside one isn't taken for it"""
    found = []
    for fb in sorted(root.glob("fb[0-9]")):
        try:
            width, height = (int(v) for v in (fb / "virtual_size").read_text().strip().split(","))
        except (OSError, ValueError):
            continue
        try:
            name = (fb / "name").read_text().strip().lower()
        except OSError:
            name = ""
        spi = any(k in name for k in ("fb_", "ili94", "piscreen", "mipi-dbi"))
        if spi or (fb.name != "fb0" and width * height <= 800 * 480):   # (fb0 unnamed: an HDMI monitor)
            found.append((0, f"/dev/{fb.name}", width, height))
        elif hdmi35(width, height):
            found.append((1, f"/dev/{fb.name}", width, height))
    return min(found)[1:] if found else None


def detect(setting="auto", model=None, screen="look"):
    """-> {"build": "pocket" or "desk", "board", "screen": (device, w, h) or None, "can": set()}

    can: "touch" and "color" (the desk box's screen), "cores" (4 of them: smooth meters, more at once),
    "usb_ports" (built-in USB ports: no hub, no 12 Mbit/s setting), "fast" (a Pi 4 or newer: more voices)."""
    model = board() if model is None else model
    screen = touchscreen() if screen == "look" else screen
    zero = "Zero" in model
    if setting in ("pocket", "desk"):
        build = setting
    else:
        build = "desk" if screen and not zero else "pocket"
    can = set()
    if build == "desk":
        can |= {"touch", "color"}
    if (os.cpu_count() or 1) >= 4 and not model.startswith("Raspberry Pi Zero W"):
        can.add("cores")
    if model and not zero:
        can.add("usb_ports")
    if fast(model):
        can.add("fast")
    return {"build": build, "board": model, "screen": screen, "can": can}
