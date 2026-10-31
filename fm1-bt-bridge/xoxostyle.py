"""The XOXO look, for the Studio's touchscreen: its themes (XOXO, the brand's, first), and its type, the XOXO Audio
Labs website's: Anton for the big things, IBM Plex Mono for the rest (vendor/fonts, both SIL OFL 1.1).

A theme is five steps of its screen colour (faintest to strongest: rules, inactive, labels, secondary text,
values), four track colours, a background and a highlight. Text is drawn in cells as before: 8 px a character
and 16 px a line at size 1, Anton at size 2 and 3 (32 and 48 px lines), its capitals centred in the line.
"""

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent / "vendor" / "fonts"


def rgb(r, g, b):
    """a colour as the panel shows it: through RGB565, so what's drawn is what the screen can show"""
    return (r >> 3 << 3, g >> 2 << 2, b >> 3 << 3)


# XOXO: the website's black, off-white, warm grey and rules, its signal red-orange used sparingly
BLACK, WHITE, GREY = (11, 11, 11), (242, 240, 235), (138, 135, 128)
SIGNAL = (255, 59, 31)

# the themes: the five steps, the four track colours, the background and the highlight
THEMES = {
    "XOXO": ([(42, 42, 40), (61, 61, 58), GREY, (200, 197, 190), WHITE],
             [SIGNAL, (226, 170, 83), WHITE, (126, 166, 201)],
             BLACK, WHITE),
    "NEON NOIR": ([rgb(46, 14, 64), rgb(92, 26, 120), rgb(186, 40, 190), rgb(255, 56, 170), rgb(60, 236, 255)],
                  [rgb(255, 40, 160), rgb(0, 224, 255), rgb(156, 84, 255), rgb(196, 255, 40)],
                  rgb(8, 4, 16), rgb(230, 250, 255)),
    "KAWAII": ([rgb(110, 84, 150), rgb(146, 116, 190), rgb(216, 174, 255), rgb(255, 168, 214), rgb(255, 252, 176)],
               [rgb(255, 168, 214), rgb(176, 208, 255), rgb(174, 255, 246), rgb(255, 252, 176)],
               rgb(74, 52, 110), rgb(255, 255, 255)),
    "BUBBLEGUM": ([rgb(176, 52, 124), rgb(214, 92, 162), rgb(255, 150, 204), rgb(255, 204, 230), rgb(255, 255, 255)],
                  [rgb(255, 255, 255), rgb(255, 172, 216), rgb(255, 84, 176), rgb(236, 150, 255)],
                  rgb(130, 22, 88), rgb(255, 255, 255)),
    "SYNTHWAVE": ([rgb(56, 20, 84), rgb(110, 32, 128), rgb(196, 52, 150), rgb(255, 92, 132), rgb(255, 192, 88)],
                  [rgb(255, 64, 150), rgb(255, 140, 40), rgb(40, 210, 255), rgb(170, 90, 255)],
                  rgb(16, 6, 34), rgb(255, 236, 200)),
    "8-BIT": ([rgb(36, 70, 36), rgb(56, 104, 48), rgb(100, 140, 24), rgb(139, 172, 15), rgb(196, 220, 90)],
              [rgb(196, 220, 90), rgb(90, 150, 70), rgb(236, 240, 180), rgb(130, 170, 30)],
              rgb(15, 40, 15), rgb(224, 240, 170)),
    "INFERNO": ([rgb(60, 10, 4), rgb(120, 24, 8), rgb(200, 56, 10), rgb(255, 130, 20), rgb(255, 222, 90)],
                [rgb(255, 60, 30), rgb(255, 150, 20), rgb(255, 230, 80), rgb(200, 40, 120)],
                rgb(14, 2, 0), rgb(255, 246, 220)),
    "TOXIC": ([rgb(30, 50, 10), rgb(60, 100, 14), rgb(110, 180, 20), rgb(170, 245, 30), rgb(220, 255, 120)],
              [rgb(170, 245, 30), rgb(190, 70, 255), rgb(255, 230, 40), rgb(40, 230, 190)],
              rgb(6, 10, 4), rgb(240, 255, 220)),
    "DEEP SEA": ([rgb(4, 40, 56), rgb(8, 74, 100), rgb(16, 130, 150), rgb(40, 200, 200), rgb(160, 250, 236)],
                 [rgb(40, 150, 255), rgb(40, 230, 180), rgb(255, 210, 120), rgb(255, 110, 140)],
                 rgb(2, 10, 22), rgb(230, 255, 252)),
}
ALL = list(THEMES)                          # MORE > THEME's list, XOXO first
DEFAULT = "XOXO"
GREYS = [(22, 22, 21), (36, 36, 34), GREY, (200, 197, 190)]   # tiles, empty, labels, text (for a black background)


def scale(c, num, den):
    return tuple(v * num // den for v in c)


def mix(c, bg, num, den):
    """num/den of c, the rest bg"""
    return tuple((v * num + b * (den - num)) // den for v, b in zip(c, bg))


class Theme:
    """the colours to draw with: c[0..4] (the screen's steps), bg, hi, track[k] (full), mid[k] (2/3), dim[k] (1/3),
    both toward the background, grey[0..3] (adjusted for the background). By name (one of ALL; another name:
    XOXO's colours), or colours of its own"""

    def __init__(self, name=DEFAULT, c=None, tracks=None, bg=None, hi=None):
        if c is None:
            c, own_tracks, own_bg, own_hi = THEMES.get(name) or THEMES[DEFAULT]
            tracks, bg, hi = tracks or own_tracks, bg or own_bg, hi or own_hi
        self.name = name                      # (colours as tuples: a theme read back from JSON has lists, which
        self.c = [tuple(x) for x in c]        # Pillow 11 refuses)
        self.bg, self.hi = tuple(bg or BLACK), tuple(hi or WHITE)
        self.track = [tuple(t) for t in (tracks or THEMES[DEFAULT][1])]
        self.mid = [mix(t, self.bg, 2, 3) for t in self.track]
        self.dim = [mix(t, self.bg, 1, 3) for t in self.track]
        self.grey = [self.toward(g) for g in GREYS]

    def toward(self, grey):
        """a grey drawn for black, the same share of the way from this background toward white (a dark one) or
        black (a light one)"""
        if self.bg == (0, 0, 0):
            return grey
        light = self.bg[0] * 299 + self.bg[1] * 587 + self.bg[2] * 114 > 128000
        return tuple(b + ((0 if light else 255) - b) * g // 255 for b, g in zip(self.bg, grey))

    def __eq__(self, other):
        return isinstance(other, Theme) and vars(self) == vars(other)


def theme_dict(t):
    return {"name": t.name, "c": t.c, "tracks": t.track, "bg": t.bg, "hi": t.hi}


def theme_load(d):
    """theme_dict's output (kept in a file) -> Theme"""
    try:
        return Theme(d["name"], d["c"], d["tracks"], d["bg"], d["hi"])
    except (KeyError, TypeError):
        return Theme()


# ---------------------------------------------------------------- the type

MONO_PX = 13.33                             # IBM Plex Mono: 8 px a character (0.6 em), as the screens are laid out


@lru_cache(None)
def mono(bold=True):
    return ImageFont.truetype(str(FONT_DIR / ("IBMPlexMono-SemiBold.ttf" if bold else "IBMPlexMono-Medium.ttf")),
                              MONO_PX)


@lru_cache(None)
def display(size):
    """Anton for a line of 16 * size px: (font, y offset that centres its capitals in the line)"""
    cell = 16 * size
    f = ImageFont.truetype(str(FONT_DIR / "Anton-Regular.ttf"), round(cell * 0.80))
    top, bottom = f.getbbox("H")[1], f.getbbox("H")[3]
    return f, (cell - (bottom - top)) // 2 - top


@lru_cache(4096)
def _mask(s, size, bold):
    """s drawn once: (its mask, its width); the screens draw the same words again and again"""
    f, dy = (mono(bold), -1) if size == 1 else display(size)
    width = int(round(f.getlength(s)))
    m = Image.new("L", (width + 2, 16 * size))
    ImageDraw.Draw(m).text((0, dy), s, font=f, fill=255)
    return m, width


PLAIN = str.maketrans({"▶": ">", "◀": "<", "▲": "^", "▼": "v", "●": "*",
                       "•": "*", "›": ">", "‹": "<", "±": "+", "…": "...",
                       "–": "-", "—": "-", "→": ">"})


def plain(s):
    """s in Latin-1, the characters both fonts have"""
    return s.translate(PLAIN).encode("latin-1", "replace").decode("latin-1")


def text_size(s, size=1):
    """(width, height) of s drawn at size (1: 16 px high, 2: 32, 3: 48)"""
    s = plain(s)
    return (_mask(s, size, True)[1] if s else 0), 16 * size


def text(img, xy, s, color, size=1, bold=True):
    """s at xy (the top left of its line): Plex Mono at size 1, Anton at 2 and 3"""
    s = plain(s)
    if not s:
        return
    m, _ = _mask(s, size, bold)
    img.paste(Image.new("RGB", m.size, tuple(color)), (int(xy[0]), int(xy[1])), m)
