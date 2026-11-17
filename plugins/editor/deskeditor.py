"""The sample editor's touch screen (the editor plug-in's): the take or sample full width, its markers dragged, big
buttons for the rest (zoom, the fades, NORMALIZE, REVERSE, its note, PLAY, SAVE, and TO PAD while the sampler
plug-in is on). Shown while one is open to edit (the app's screen "editor": the EDITOR tab, a pad's TRIM). OPEN
lists the SAMPLES and TAKES (the recordings) to edit. What it edits and the sums are the Studio's own
(sampleui.SampleEditor, sampler.py)."""
from pathlib import Path

import library
import xoxostyle as st
from deskplugins import Tab

W, H, HDR_H = 480, 320, 34
ROW_H = 46


class EditorScreen(Tab):
    def __init__(self, ui, studio):
        super().__init__(ui, studio)
        self.ed_view, self.ed_wave, self.ed_drag = None, None, None   # the zoom, the waveform, a marker held
        self.ed_files = False                   # OPEN: the list instead of the take
        self.ed_to_pad = False                  # TO PAD: choosing a pad
        self.browse, self.browse_top = "samples", 0   # OPEN's list: samples or takes, its scroll
        self.trimming = None                    # the sampler's PADS tab that asked to TRIM a pad, or None

    @property
    def app(self):
        return self.ui.app

    def view(self):
        return (self.ed_view, self.ed_files, self.browse, self.browse_top, self.ed_to_pad,
                self.trimming and self.trimming.pad_trim)

    def reset(self):
        self.ed_view, self.ed_wave, self.ed_drag, self.ed_to_pad = None, None, None, False

    def open_last(self):
        """EDITOR: the file last edited, or OPEN's list the first time"""
        a = self.app
        last = a.state.get("editor_last")
        self.trimming = None
        self.reset()
        if last and (library.folder(last[1]) / last[0]).exists():
            self.ed_files = False
            a.open_editor(*last)
        else:
            a.ed, a.screen, self.ed_files = None, "editor", True

    def edit(self, name, folder, pads=None):
        """a file into the editor (remembered: EDITOR opens it again); pads: the PADS tab trimming one of its pads"""
        a = self.app
        self.trimming, self.ed_files = pads, False
        self.reset()
        a.state["editor_last"] = [name, folder]
        a.save_settings()
        a.open_editor(name, folder)

    # ---- OPEN: the samples and takes

    def editor_files(self):
        """OPEN: the list, or back to the take"""
        self.ed_files = not self.ed_files or not self.app.ed

    def browse_to(self, name):
        self.browse, self.browse_top = name, 0

    def browse_files(self):
        """[(file name, its folder, what shows on the right)] of the section, newest first"""
        from meters import clock
        listing = library.listing()
        if self.browse == "samples":
            return [(s["name"], "samples", "") for s in listing["samples"]]
        return [(r["name"], "recordings", clock(r.get("seconds", 0))) for r in listing["recordings"]]

    def draw_files(self, img, d):
        """OPEN: SAMPLES or TAKES, newest first; tap one to edit it"""
        t = self.theme
        for k, (name, label) in enumerate((("samples", "SAMPLES"), ("takes", "TAKES"))):
            self.button(img, d, (8 + k * 120, HDR_H + 4, 122 + k * 120, HDR_H + 38), label,
                        lambda name=name: self.browse_to(name), on=self.browse == name, key=("browse", name))
        files = self.browse_files()
        rows, top = 5, HDR_H + 44
        self.browse_top = max(0, min(self.browse_top, len(files) - rows))
        for k, (name, folder, right) in enumerate(files[self.browse_top:self.browse_top + rows]):
            y = top + k * ROW_H
            box = (8, y, W - 64, y + ROW_H - 6)
            hot = self.ui.lit(("file", name))
            d.rectangle(box, fill=t.hi if hot else t.grey[0])
            st.text(img, (box[0] + 12, y + 12), Path(name).stem.upper()[:26], t.bg if hot else t.c[4])
            tag = (right + "  EDIT").strip()
            st.text(img, (box[2] - 12 - st.text_size(tag)[0], y + 12), tag, t.bg if hot else t.c[3])
            self.widget(box, "tap", lambda name=name, folder=folder: self.edit(name, folder), ("file", name))
        if not files:
            self.centre(img, (0, top, W, H - 20), "NO SAMPLES YET" if self.browse == "samples"
                        else "NO RECORDINGS YET: RECORD ONE ON RECORDER", t.c[2])
        if len(files) > rows:
            self.button(img, d, (W - 56, top, W - 8, top + 2 * ROW_H - 6), "^",
                        lambda: self.browse_scroll(-3), key="browse-up")
            self.button(img, d, (W - 56, top + 3 * ROW_H, W - 8, top + 5 * ROW_H - 6), "v",
                        lambda: self.browse_scroll(3), key="browse-down")

    def browse_scroll(self, step):
        self.browse_top = max(0, self.browse_top + step)

    def pads(self):
        """the sampler plug-in's PADS tab while it's on (TO PAD, a pad's TRIM), or None"""
        return self.ui.plugin_tab("PADS")

    def to_pad(self, i):
        """TO PAD: the edit saved as a new sample, on the sampler's pad i, and that pad's page"""
        a = self.app
        self.ed_to_pad = False
        pads = self.pads()
        a.editor_save()
        saved = a.ed and a.ed.get("saved")
        if not saved or pads is None:
            return
        self.trimming = None
        self.reset()
        a.editor_close()
        a.screen = "status"
        pads.to_pad(i, saved)

    def draw(self, img, d, now):
        import meters
        a, t, ed = self.app, self.theme, self.app.ed
        home = (self.ui.tab == "EDITOR" and self.trimming is None
                and not (self.ed_files and ed))     # (the EDITOR tab's: back is HOME, as the other tabs)
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< HOME" if home else "< BACK", self.editor_back, key="ed-back")
        self.button(img, d, (90, 3, 170, HDR_H - 5), "OPEN", self.editor_files, on=self.ed_files or not ed,
                    key="ed-open")
        if self.ed_files or not ed:                   # OPEN: the samples and takes to edit
            st.text(img, (180, 9), "SAMPLE EDITOR: PICK A FILE", t.hi)
            d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
            return self.draw_files(img, d)
        if ed["loading"] or ed["error"]:
            text = "LOADING THE TAKE..." if ed["loading"] else "CAN'T OPEN IT: " + str(ed["error"])[:30]
            st.text(img, (180, 9), ed["name"][:30], t.c[3])
            self.centre(img, (0, HDR_H, W, H), text, t.hi if ed["error"] else t.c[3])
            return
        length = ed["end"] - ed["start"]
        st.text(img, (180, 9), Path(ed["name"]).stem[:22], t.c[3])
        tag = f"{length:.2f}S"
        tw = st.text_size(tag)[0]
        st.text(img, (W - tw - 10, 9), tag, t.hi)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        # the waveform, in the view (zoomed in or the whole take)
        v0, v1 = self.ed_view or (0.0, ed["seconds"])
        top, bottom = HDR_H + 6, HDR_H + 132
        mid, half = (top + bottom) // 2, (bottom - top) // 2 - 4
        wave = self.editor_wave(ed, v0, v1)

        def x_of(sec):
            return int((sec - v0) / max(1e-6, v1 - v0) * (W - 1))
        sx, ex = x_of(ed["start"]), x_of(ed["end"])
        d.rectangle((max(0, sx), top, min(W - 1, ex), bottom), fill=t.grey[0])
        for i, (lo, hi) in enumerate(wave):
            inside = sx <= i <= ex
            if inside or i % 2 == 0:
                d.line((i, mid - int(hi * half), i, mid - int(lo * half)), fill=t.c[4] if inside else t.c[1])
        for fade, at, sign in ((ed["fade_in"], ed["start"], 1), (ed["fade_out"], ed["end"], -1)):
            if fade > 0:                              # the fades: a ramp from the marker
                d.line((x_of(at), bottom, x_of(at + sign * fade), top), fill=t.track[2], width=2)
        for x, which in ((sx, "start"), (ex, "end")):
            if 0 <= x < W:
                hot = self.ed_drag == which
                colour = t.hi if hot else t.track[0 if which == "start" else 3]
                d.rectangle((x - 1, top, x + 1, bottom), fill=colour)
                flag = (x - 14, top - 4, x + 14, top + 18) if which == "start" else (x - 14, bottom - 18, x + 14,
                                                                                      bottom + 4)
                d.rectangle(flag, fill=colour)
                st.text(img, (x - 4, flag[1] + 3), "S" if which == "start" else "E", t.bg)
        self.widget((0, top - 6, W - 1, bottom + 6), "drag", self.editor_drag, "ed-wave")
        st.text(img, (6, bottom + 6), f"{ed['start']:.2f}", t.track[0])
        end_text = f"{ed['end']:.2f}"
        st.text(img, (W - 6 - st.text_size(end_text)[0], bottom + 6), end_text, t.track[3])
        view_text = "ALL" if self.ed_view is None else f"{v0:.2f} - {v1:.2f}"
        st.text(img, ((W - st.text_size(view_text)[0]) // 2, bottom + 6), view_text, t.c[2])
        # the controls: three rows of big buttons
        y1, y2, y3 = bottom + 26, bottom + 66, bottom + 106
        self.button(img, d, (4, y1, 64, y1 + 36), "-", lambda: self.editor_zoom(2.0), key="ed-zoom-")
        self.button(img, d, (68, y1, 128, y1 + 36), "+", lambda: self.editor_zoom(0.5), key="ed-zoom+")
        self.button(img, d, (132, y1, 192, y1 + 36), "ALL", lambda: self.editor_zoom(None), key="ed-all")
        for x0, field, label in ((200, "fade_in", "IN"), (340, "fade_out", "OUT")):
            st.text(img, (x0, y1 + 2), label, t.c[2])
            st.text(img, (x0, y1 + 20), f"{round(ed[field] * 1000)}MS", t.hi)
            self.button(img, d, (x0 + 62, y1, x0 + 96, y1 + 36), "-",
                        lambda field=field: a.editor_change(field, -5), key=("ed-", field))
            self.button(img, d, (x0 + 100, y1, x0 + 134, y1 + 36), "+",
                        lambda field=field: a.editor_change(field, 5), key=("ed+", field))
        self.button(img, d, (4, y2, 154, y2 + 36), "NORMALIZE", lambda: a.editor_change("normalize", 1),
                    on=ed["normalize"], key="ed-norm")
        self.button(img, d, (160, y2, 270, y2 + 36), "REVERSE", lambda: a.editor_change("reverse", 1),
                    on=ed["reverse"], key="ed-rev")
        note = "NONE" if ed["note"] is None else meters.note_name(ed["note"])
        found = ed["note"] is not None and ed["note"] == ed["found"]
        self.button(img, d, (276, y2, 316, y2 + 36), "<", lambda: a.editor_change("note", -1), key="ed-note-")
        st.text(img, (322, y2 + 2), "NOTE", t.c[2])
        st.text(img, (322, y2 + 20), note + (" FOUND" if found else ""), t.hi)
        self.button(img, d, (436, y2, 476, y2 + 36), ">", lambda: a.editor_change("note", 1), key="ed-note+")
        playing = a.player.playing()
        self.button(img, d, (4, y3, 156, y3 + 36), "STOP" if playing else "PLAY",
                    lambda: a.player.stop() if a.player.playing() else a.editor_preview(), on=playing,
                    key="ed-play")
        trim = self.trimming and self.trimming.pad_trim
        save = f"SAVE ON PAD {trim + 1}" if trim is not None else "SAVE"   # (a pad's trim)
        pads = self.pads()
        self.button(img, d, (162, y3, 318 if pads else 476, y3 + 36), save, a.editor_save, color=t.track[1],
                    key="ed-save")
        if pads:                                # TO PAD: while the sampler plug-in is on
            self.button(img, d, (324, y3, 476, y3 + 36), "TO PAD", self.choose_pad, color=t.track[0],
                        key="ed-to-pad")
        if self.ed_to_pad and pads:                   # which pad: over the controls
            self.draw_pad_choice(img, d, HDR_H + 134)

    def choose_pad(self):
        self.ed_to_pad = not self.ed_to_pad

    def draw_pad_choice(self, img, d, top):
        """the 16 pads, MPC order (pad 1 bottom left), to put the edit on one"""
        t, kit = self.theme, self.pads().kit()
        d.rectangle((0, top, W, H), fill=t.bg)
        st.text(img, (8, top + 2), "PUT IT ON PAD:", t.hi)
        self.button(img, d, (W - 96, top, W - 4, top + 20), "BACK", self.choose_pad, key="ed-pad-cancel")
        gw, gh = (W - 8) // 8, (H - top - 26) // 2
        for i in range(16):
            row, col = 1 - i // 8, i % 8
            box = (4 + col * gw + 1, top + 24 + row * gh + 1, 4 + (col + 1) * gw - 2, top + 24 + (row + 1) * gh - 2)
            colour = t.track[(3 - i // 4) % 4]
            hot = self.ui.lit(("ed-pad", i))
            used = bool(kit["pads"][i]["sample"])
            d.rectangle(box, fill=t.hi if hot else t.dim[(3 - i // 4) % 4] if used else t.grey[0], outline=colour,
                        width=2)
            self.centre(img, box, str(i + 1), t.bg if hot else colour)
            self.widget(box, "tap", lambda i=i: self.to_pad(i), ("ed-pad", i))

    def editor_wave(self, ed, v0, v1):
        """(low, high) a screen column for the view, scaled to the whole take's peak (so zooming in doesn't
        make a quiet part look loud); kept until the view changes"""
        import numpy as np
        key = (id(ed["x"]), v0, v1)
        if self.ed_wave and self.ed_wave[0] == key:
            return self.ed_wave[1]
        x = ed["x"]
        if "peak" not in ed:
            ed["peak"] = max(1.0, float(np.abs(x).max())) if len(x) else 1.0   # (an empty file: a flat line, not a
                                                                                   # crash: the app died on one, 2026-11-03)
        part = x[int(v0 * ed["rate"]):max(int(v0 * ed["rate"]) + W, int(v1 * ed["rate"]))]
        edges = np.linspace(0, len(part), W + 1).astype(int)[:-1]
        if len(part) < W:
            wave = [(0.0, 0.0)] * W
        else:
            wave = list(zip((np.minimum.reduceat(part, edges) / ed["peak"]).tolist(),
                            (np.maximum.reduceat(part, edges) / ed["peak"]).tolist()))
        self.ed_wave = (key, wave)
        return wave

    def editor_drag(self, phase, x, y):
        """a finger on the waveform: takes the nearer marker (down) and moves it (move); lifted: lets it go"""
        import sampler
        ed = self.app.ed
        if phase == "up":
            self.ed_drag = None
            return
        v0, v1 = self.ed_view or (0.0, ed["seconds"])
        sec = v0 + max(0, min(W - 1, x)) / (W - 1) * (v1 - v0)
        if phase == "down":
            self.ed_drag = "start" if abs(sec - ed["start"]) <= abs(sec - ed["end"]) else "end"
        if self.ed_drag == "start":
            ed["start"] = round(min(max(0.0, sec), ed["end"] - sampler.SHORTEST), 3)
        elif self.ed_drag == "end":
            ed["end"] = round(max(min(ed["seconds"], sec), ed["start"] + sampler.SHORTEST), 3)

    def editor_zoom(self, factor):
        """factor 0.5: in (around the selection), 2: out; None: the whole take"""
        ed = self.app.ed
        if factor is None:
            self.ed_view = None
            return
        v0, v1 = self.ed_view or (0.0, ed["seconds"])
        width = min(ed["seconds"], max(0.05, (v1 - v0) * factor))
        centre = (ed["start"] + ed["end"]) / 2 if factor < 1 else (v0 + v1) / 2
        v0 = min(max(0.0, centre - width / 2), ed["seconds"] - width)
        self.ed_view = None if width >= ed["seconds"] else (round(v0, 4), round(v0 + width, 4))

    def editor_back(self):
        if self.ed_files and self.app.ed:             # the OPEN list: back to the take
            self.ed_files = False
            return
        self.ed_files = False
        self.reset()
        a, trimming = self.app, self.trimming
        saved = a.ed and a.ed.get("saved")
        self.trimming = None
        a.editor_close()
        a.screen = "status"
        if trimming is not None:                   # a pad's TRIM: its new sample on the pad, its page again
            trimming.trimmed(saved)
        else:
            self.ui.open_tab("HOME")
