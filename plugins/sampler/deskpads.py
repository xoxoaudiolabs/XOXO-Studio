"""The sampler plug-in's PADS tab: the 4x4 sampler (pads.py) by touch, full screen (deskplugins.Tab; what it doesn't
have itself, such as the widgets, it takes from the Studio's screen, ui).

The 16 pads in four rows of the theme's track colours (pad 1 bottom left, as on an MPC), lit while they sound (from
a tap or from MIDI: notes 36-51 while MIDI IN is on). Above them: < HOME, the kit's name (KITS: load one, save this
one, start a new one), RPT (note repeat: a pad held plays again at its division), FX (the punch-in FX, padfx.py,
sixteen of SLOOP's, on the pads' sound: hold one, or LATCH it on), MIDI IN (the routes' SMP notes play the pads; off,
only the clock reaches them), EDIT (then a pad: its own page: sample, level, pan, tune, mode, attack, release,
choke, reverse; PLAY, SAMPLE from any source, TRIM in the sample editor (while that plug-in is on), CLEAR). An empty
pad opens its page anyway.
"""

from pathlib import Path

import library
import meters
import pads
import xoxostyle as st
from deskplugins import Tab

W, H, HDR_H, TAB_H = 480, 320, 34, 44
ROW_H, ROWS = 46, 4
PAD_ROWS = [("sample", "SAMPLE"), ("level", "LEVEL"), ("pan", "PAN"), ("tune", "TUNE"), ("mode", "MODE"),
            ("attack", "ATTACK"), ("release", "RELEASE"), ("choke", "CHOKE"), ("reverse", "REVERSE")]
STEPS = {"level": 5, "pan": 5, "tune": 1, "attack": 10, "release": 25}


class PadsTab(Tab):
    """the PADS tab: tab(ui, studio), the sampler's process (pads.PadProcess) its studio.process()"""
    what = "the pads"                           # (a tab that plays: the Pi Bluetooth warning names it)

    def __init__(self, ui, studio):
        super().__init__(ui, studio)
        self.pad_edit, self.pad_mode = None, False     # the pad whose page is open; EDIT on
        self.pad_top, self.kits_open, self.kits_top = 0, False, 0
        self.pad_rec = None                            # sampling into a pad: {"pad", "rec", "path", "source"}
        self.pad_trim = None                           # the pad whose sample the editor is trimming
        self.pad_pick_source = None                    # choosing what to sample: the pad
        self.fx_open = False                           # the FX page
        self.fx_on, self.fx_latch = None, False        # the punch-in FX on; LATCH (a tap holds it)

    def __getattr__(self, name):                       # (the Studio's screen's: its widgets, theme, app ...)
        if name in ("ui", "studio"):
            raise AttributeError(name)
        return getattr(self.ui, name)

    @property
    def proc(self):
        return self.studio.process()

    def kit(self):
        import padkit
        return padkit.kit(self.studio)

    def set_kit(self, kit):
        import padkit
        padkit.set_kit(self.studio, kit)

    def view(self, now):
        p = self.proc
        rec = self.pad_rec and (self.pad_rec["pad"], int(self.pad_rec["rec"].seconds()))
        return (str(self.studio.settings.get("kit")), tuple(p.sounding) if p else (), self.pad_edit, self.pad_mode,
                self.pad_top, self.kits_open and self.kits_top, self.kits_open, rec, self.pad_pick_source,
                self.ui.held and self.ui.held[3], self.fx_open, self.fx_on, self.fx_latch,
                self.studio.settings.get("repeat"), bool(self.studio.settings.get("midi_in")))

    # ---- the grid

    def draw(self, img, d, now):
        if self.pad_rec is not None:
            return self.draw_pad_rec(img, d, now)
        if self.pad_pick_source is not None:
            return self.draw_pick_source(img, d)
        if self.kits_open:
            return self.draw_kits(img, d)
        if self.pad_edit is not None:
            return self.draw_pad_page(img, d)
        if self.fx_open:
            return self.draw_fx(img, d, now)
        t = self.theme                          # the 16 pads, 4x4
        kit = self.kit()
        self.button(img, d, (4, 3, 74, HDR_H - 5), "< HOME", self.home, key="pads-home")
        self.button(img, d, (80, 3, 168, HDR_H - 5), kit["name"][:10], self.open_kits, key="kits")   # its kits
        repeat = self.studio.settings.get("repeat")
        midi_in = bool(self.studio.settings.get("midi_in"))
        buttons = [("RPT" if repeat is None else pads.DIVS[repeat], self.toggle_repeat, repeat is not None,
                    "pad-repeat"),
                   ("FX", self.open_fx, self.fx_on is not None, "fx-open"),
                   ("MIDI IN", self.toggle_midi_in, midi_in, "pads-midi-in"),
                   ("EDIT", self.toggle_pad_mode, self.pad_mode, "pad-mode")]
        for k, (label, action, on, key) in enumerate(buttons):     # right to left from EDIT
            x1 = W - 4 - (len(buttons) - 1 - k) * 74
            self.button(img, d, (x1 - 70, 3, x1, HDR_H - 5), label, action, on=on, key=key)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        p = self.proc
        sounding = set(p.sounding) if p else set()
        gw, gh = (W - 10) // 4, (H - HDR_H - 8) // 4      # the whole height: no tab bar under the pads
        for i in range(pads.PADS):
            row, col = 3 - i // 4, i % 4                   # pad 1 bottom left, as on an MPC
            x0, y0 = 5 + col * gw, HDR_H + 4 + row * gh
            box = (x0 + 2, y0 + 2, x0 + gw - 3, y0 + gh - 3)
            pad = kit["pads"][i]
            colour = t.track[row % 4]
            lit = i in sounding or self.lit(("pad", i))
            fill = t.hi if lit else (t.dim[row % 4] if pad["sample"] else t.grey[0])
            d.rectangle(box, fill=fill, outline=colour if pad["sample"] else t.c[0], width=2)
            st.text(img, (box[0] + 6, box[1] + 4), str(i + 1), t.bg if lit else colour)
            name = (Path(pad["sample"]).stem[:12] if pad["sample"]
                    else "TAP TO SET")
            st.text(img, (box[0] + 6, box[3] - 20), name.upper(), t.bg if lit else (t.c[4] if pad["sample"] else t.c[1]))
            if self.pad_mode or not pad["sample"]:         # EDIT, or an empty pad: its page (to sample it)
                self.widget(box, "tap", lambda i=i: self.open_pad(i), ("pad", i))
            else:
                self.widget(box, "gate", lambda down, i=i: self.hit(i, down), ("pad", i))

    def hit(self, i, down):
        p = self.proc
        if p:
            p.send("tap", i, 110) if down else p.send("untap", i)

    def toggle_repeat(self):
        """note repeat: off, 1/8, 1/16, 1/32, 16T, 8T, 1/4, off: a pad held plays again at it"""
        settings = self.studio.settings
        order = [None, 1, 2, 3, 5, 4, 0]
        now = settings.get("repeat")
        settings["repeat"] = order[(order.index(now) + 1) % len(order)] if now in order else None
        self.studio.save()
        if self.proc:
            self.proc.send("repeat", settings["repeat"])

    def toggle_midi_in(self):
        """MIDI IN: the routes' SMP notes play the pads (on) or not (off: only the clock reaches them)"""
        settings = self.studio.settings
        settings["midi_in"] = not settings.get("midi_in")
        self.studio.save()
        if self.proc:
            self.proc.send("midi_in", settings["midi_in"])

    def toggle_pad_mode(self):
        self.pad_mode = not self.pad_mode

    def open_pad(self, i):
        self.pad_edit, self.pad_top = i, 0

    # ---- a pad's page

    def pad_value(self, pad, key):
        v = pad[key]
        if key == "sample":
            return Path(v).stem.upper()[:16] if v else "NONE"
        if key in ("attack", "release"):
            return f"{v}MS"
        if key == "pan":
            return "C" if v == 0 else f"{'L' if v < 0 else 'R'}{abs(v)}"
        if key == "tune":
            return f"{v:+d} ST"
        if key == "level":
            return f"{v}%"
        if key == "choke":
            return "OFF" if not v else f"GROUP {v}"
        if key == "reverse":
            return "ON" if v else "OFF"
        return str(v).upper()

    def draw_pad_page(self, img, d):
        t = self.theme
        i = self.pad_edit
        kit = self.kit()
        pad = kit["pads"][i]
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< BACK", self.close_pad, key="pad-back")
        st.text(img, (96, 9), f"PAD {i + 1}", t.track[(3 - i // 4) % 4])
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        top = max(0, min(self.pad_top, len(PAD_ROWS) - ROWS))
        for k, (key, label) in enumerate(PAD_ROWS[top:top + ROWS]):
            y = HDR_H + 4 + k * ROW_H
            box = (8, y, W - 64, y + ROW_H - 6)
            d.rectangle(box, fill=t.grey[0])
            st.text(img, (box[0] + 12, y + 12), label, t.c[4])
            value = self.pad_value(pad, key)
            if key in STEPS:                                 # numbers: - value +
                minus, plus = (box[2] - 160, y + 3, box[2] - 116, y + ROW_H - 9), (box[2] - 48, y + 3, box[2] - 4,
                                                                                   y + ROW_H - 9)
                self.button(img, d, minus, "-", lambda key=key: self.pad_step(key, -1), key=("pad-", key))
                self.button(img, d, plus, "+", lambda key=key: self.pad_step(key, 1), key=("pad+", key))
                vw = st.text_size(value[:7])[0]
                st.text(img, ((minus[2] + plus[0] - vw) // 2, y + 12), value[:7], t.hi)
            else:                                            # a choice or the sample: tap the row
                vw = st.text_size(value)[0]
                st.text(img, (box[2] - 12 - vw, y + 12), value, t.c[3])
                self.widget(box, "tap", lambda key=key: self.pad_choose(key), ("pad-row", key))
        self.button(img, d, (W - 56, HDR_H + 4, W - 8, HDR_H + 2 * ROW_H - 2), "^",
                    lambda: self.pad_scroll(-2), key="pad-up")
        self.button(img, d, (W - 56, HDR_H + 2 * ROW_H + 2, W - 8, HDR_H + 4 * ROW_H - 6), "v",
                    lambda: self.pad_scroll(2), key="pad-down")
        y = H - 92
        actions = [("PLAY", lambda: self.hit(i, True)), ("SAMPLE", lambda: self.pick_source(i))]
        if self.ui.plugin_tab("EDITOR") is not None:         # (TRIM: in the sample editor, while it's on)
            actions.append(("TRIM", lambda: self.trim(i)))
        actions.append(("CLEAR", lambda: self.clear_pad(i)))
        bw = (W - 16) // len(actions)
        for k, (label, action) in enumerate(actions):
            self.button(img, d, (8 + k * bw, y, 8 + (k + 1) * bw - 6, y + 40), label, action,
                        color=(255, 112, 92) if label == "SAMPLE" else None, key=("pad-act", label))
        tip = "NOTE " + meters.note_name(pads.note_of(i)) + " PLAYS IT"
        st.text(img, ((W - st.text_size(tip)[0]) // 2, H - 40), tip, t.c[2])

    def pad_scroll(self, step):
        self.pad_top = max(0, min(len(PAD_ROWS) - ROWS, self.pad_top + step))

    def edit_pad(self, **changes):
        kit = self.kit()
        kit["pads"][self.pad_edit].update(changes)
        self.set_kit(kit)

    def pad_step(self, key, step):
        pad = self.kit()["pads"][self.pad_edit]
        self.edit_pad(**{key: pad[key] + step * STEPS[key]})          # (clean_kit keeps it in range)

    def pad_choose(self, key):
        a = self.app
        pad = self.kit()["pads"][self.pad_edit]
        if key == "mode":
            self.edit_pad(mode=pads.MODES[(pads.MODES.index(pad["mode"]) + 1) % len(pads.MODES)])
        elif key == "choke":
            self.edit_pad(choke=(pad["choke"] + 1) % 5)
        elif key == "reverse":
            self.edit_pad(reverse=not pad["reverse"])
        elif key == "sample":                                # the samples folder, newest first
            items = [(Path(s["name"]).stem, "", s["name"]) for s in library.listing()["samples"]]
            a.open_pick("Sample for pad", items, self.assign_sample, "No samples yet: SAMPLE one")

    def assign_sample(self, name):
        self.edit_pad(sample=str(library.folder("samples") / name))
        self.app.screen = "status"

    def clear_pad(self, i):
        kit = self.kit()
        kit["pads"][i] = dict(pads.DEFAULT_PAD)
        self.set_kit(kit)

    def close_pad(self):
        self.pad_edit = None

    def trim(self, i):
        """TRIM: the pad's sample in the sample editor (the editor plug-in's), back here when it closes"""
        a = self.app
        sample = self.kit()["pads"][i]["sample"]
        if not sample or not Path(sample).exists():
            a.say("No sample on this pad", 2)
            return
        path = Path(sample)
        if path.parent != library.folder("samples"):
            a.say("Only samples in the samples folder", 2)
            return
        editor = self.ui.plugin_tab("EDITOR")
        if editor is None:
            return
        self.pad_trim = i
        editor.edit(path.name, "samples", pads=self)

    def trimmed(self, saved):
        """the editor closed: a trimmed pad's new sample (saved, or None) goes back on its pad, its page shown"""
        if self.pad_trim is not None and saved:
            kit = self.kit()
            kit["pads"][self.pad_trim]["sample"] = str(saved)
            self.set_kit(kit)
        if self.pad_trim is not None:
            self.pad_edit = self.pad_trim
        self.pad_trim = None
        self.ui.open_tab("PADS")

    def to_pad(self, i, saved):
        """the editor's TO PAD: its edit, saved as a new sample, on pad i; its page shown"""
        kit = self.kit()
        kit["pads"][i]["sample"] = str(saved)
        self.set_kit(kit)
        self.pad_trim, self.kits_open, self.pad_edit, self.pad_mode = None, False, i, False
        self.ui.open_tab("PADS")
        self.app.say(f"Pad {i + 1}: {Path(saved).stem[:16]}", 2)

    # ---- sampling into a pad: choose a source, record, stop

    def pick_source(self, i):
        if not self.app.mix_channels():
            self.app.say("Nothing to sample: no sound source", 2)
            return
        self.pad_pick_source = i

    def draw_pick_source(self, img, d):
        a, t = self.app, self.theme
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< BACK", self.cancel_pick_source, key="src-back")
        st.text(img, (96, 9), f"SAMPLE PAD {self.pad_pick_source + 1} FROM", t.hi)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        sources = [(k, n) for k, n in a.mix_channels() if k != "u-xo4"][:5]   # (not the pads' own channel)
        for k, (key, node) in enumerate(sources):
            y = HDR_H + 4 + k * ROW_H
            box = (8, y, W - 8, y + ROW_H - 6)
            hot = self.lit(("src", key))
            d.rectangle(box, fill=t.hi if hot else t.grey[0])
            st.text(img, (box[0] + 12, y + 12), a.channel_name(key, node), t.bg if hot else t.c[4])
            self.widget(box, "tap", lambda key=key, node=node: self.start_pad_rec(key, node), ("src", key))

    def cancel_pick_source(self):
        self.pad_pick_source = None

    def start_pad_rec(self, key, node):
        from meters import Recorder
        a = self.app
        i, self.pad_pick_source = self.pad_pick_source, None
        path = Path(library.RUNTIME) / f"fm1-pad-{i + 1}.wav"
        rec = Recorder()
        if not rec.start(node["name"], path, a.state["audio_rate"]):
            a.say("Can't record (pw-record?)", 2)
            return
        self.pad_rec = {"pad": i, "rec": rec, "path": path, "source": a.channel_name(key, node)}

    def draw_pad_rec(self, img, d, now):
        t, r = self.theme, self.pad_rec
        st.text(img, (12, 9), f"SAMPLING PAD {r['pad'] + 1}", (255, 112, 92))
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        st.text(img, (16, HDR_H + 20), "FROM " + r["source"], t.c[3])
        secs = r["rec"].seconds()
        text = f"{int(secs) // 60}:{int(secs) % 60:02}"
        self.centre(img, (0, HDR_H + 40, W, HDR_H + 150), text, t.hi, 4)
        st.text(img, (16, HDR_H + 160), "PLAY THE SOUND, THEN STOP. THE SILENCE", t.c[2])
        st.text(img, (16, HDR_H + 180), "AROUND IT IS TRIMMED OFF.", t.c[2])
        self.button(img, d, (8, H - 54, W - 8, H - 8), "STOP", self.stop_pad_rec, color=(255, 112, 92),
                    on=True, key="pad-stop")

    def stop_pad_rec(self):
        import sampler
        a, r = self.app, self.pad_rec
        self.pad_rec = None
        r["rec"].stop()
        try:
            rate, x = sampler.load(r["path"])
            start, end, note = sampler.opening(r["path"], x, rate)
            out = sampler.save_from(x, rate, f"pad{r['pad'] + 1}", note, start, end, **sampler.DEFAULT_EDIT)
        except (OSError, ValueError, EOFError) as e:
            a.say(f"Couldn't sample: {e}"[:40], 3)
            return
        finally:
            Path(r["path"]).unlink(missing_ok=True)
        kit = self.kit()
        kit["pads"][r["pad"]]["sample"] = str(out)
        self.set_kit(kit)
        self.pad_edit = r["pad"]
        a.say(f"Pad {r['pad'] + 1}: {out.stem[:16]}", 2.5)

    # ---- FX: the punch-in FX (padfx.py) on the pads' sound, held (or latched: one finger on this screen)

    def open_fx(self):
        """the FX page: the pads' punch-in FX, on and LATCH"""
        self.fx_open = True

    def fx_state(self):
        """(the FX on, LATCH)"""
        return self.fx_on, self.fx_latch

    def close_fx(self):
        self.fx_open = False                           # (a latched FX stays on: play the pads under it)

    def draw_fx(self, img, d, now):
        import padfx
        t = self.theme
        fx_on, latch = self.fx_state()
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< BACK", self.close_fx, key="fx-back")
        st.text(img, (96, 9), "PADS FX", t.hi)
        st.text(img, (230, 9), self.tempo_text()[:12], t.c[2])
        self.button(img, d, (W - 104, 3, W - 4, HDR_H - 5), "LATCH", self.toggle_fx_latch, on=latch,
                    key="fx-latch")
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        gw, gh = (W - 10) // 4, (H - HDR_H - 8) // 4
        for i, name in enumerate(padfx.NAMES):
            row, col = i // 4, i % 4
            x0, y0 = 5 + col * gw, HDR_H + 4 + row * gh
            box = (x0 + 2, y0 + 2, x0 + gw - 3, y0 + gh - 3)
            colour = t.track[row % 4]
            on = fx_on == i
            d.rectangle(box, fill=colour if on else t.dim[row % 4], outline=colour, width=2)
            st.text(img, (box[0] + 6, box[1] + 4), str(i + 1), t.bg if on else colour)
            st.text(img, (box[0] + 6, box[3] - 20), name, t.bg if on else t.c[4])
            if latch:
                self.widget(box, "tap", lambda i=i: self.fx_tap(i), ("fx", i))
            else:
                self.widget(box, "gate", lambda down, i=i: self.fx_hold(i, down), ("fx", i))

    def fx_send(self, fx):
        self.fx_on = fx
        if self.proc:
            self.proc.send("fx", fx)

    def fx_hold(self, i, down):
        self.fx_send(i if down else None)

    def fx_tap(self, i):
        """LATCH: a tap holds it on, a tap on it again (or another) lets go / changes"""
        self.fx_send(None if self.fx_state()[0] == i else i)

    def toggle_fx_latch(self):
        fx_on, latch = self.fx_state()
        self.fx_latch = not latch
        if latch and fx_on is not None:                # LATCH off: what it held lets go
            self.fx_send(None)

    # ---- kits

    def open_kits(self):
        self.kits_open = True

    def draw_kits(self, img, d):
        t = self.theme
        self.button(img, d, (4, 3, 84, HDR_H - 5), "< BACK", self.close_kits, key="kits-back")
        st.text(img, (96, 9), "KITS", t.hi)
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        every = pads.list_kits()
        self.kits_top = max(0, min(self.kits_top, len(every) - ROWS))
        kits = every[self.kits_top:self.kits_top + ROWS]
        current = self.kit()["name"]
        right = W - 64 if len(every) > ROWS else W - 8      # (room for ^ v when they don't all fit)
        for k, name in enumerate(kits):
            y = HDR_H + 4 + k * ROW_H
            box = (8, y, right, y + ROW_H - 6)
            hot = self.lit(("kit", name))
            on = name.replace("-", " ").upper() == current.upper()
            d.rectangle(box, fill=t.hi if hot else t.grey[1] if on else t.grey[0])
            st.text(img, (box[0] + 12, y + 12), name.upper(), t.bg if hot else t.c[4])
            st.text(img, (box[2] - 60, y + 12), "LOAD", t.bg if hot else t.c[3])
            self.widget(box, "tap", lambda name=name: self.load_kit(name), ("kit", name))
        if not kits:
            self.centre(img, (0, HDR_H, W, H - 60), "NO KITS SAVED YET", t.c[2])
        if len(every) > ROWS:
            self.button(img, d, (W - 56, HDR_H + 4, W - 8, HDR_H + 2 * ROW_H - 2), "^",
                        lambda: self.kits_scroll(-2), key="kits-up")
            self.button(img, d, (W - 56, HDR_H + 2 * ROW_H + 2, W - 8, HDR_H + 4 * ROW_H - 6), "v",
                        lambda: self.kits_scroll(2), key="kits-down")
        y = H - 54
        self.button(img, d, (8, y, W // 2 - 4, H - 8), "SAVE " + current[:10], self.save_kit, key="kit-save")
        self.button(img, d, (W // 2 + 4, y, W - 8, H - 8), "NEW KIT", self.new_kit, key="kit-new")

    def close_kits(self):
        self.kits_open = False

    def kits_scroll(self, step):
        self.kits_top = max(0, self.kits_top + step)

    def load_kit(self, name):
        kit = pads.load_kit(pads.kits_folder() / f"{name}.json")
        if kit:
            self.set_kit(kit)
            self.app.say(f"Kit {kit['name']}", 1.5)
        self.kits_open = False

    def save_kit(self):
        path = pads.save_kit(self.kit())
        self.app.say(f"Saved {path.stem}", 1.5)

    def new_kit(self):
        names = {n.upper() for n in pads.list_kits()}
        n = 1
        while f"KIT-{n}" in names:
            n += 1
        self.set_kit(pads.empty_kit(f"KIT {n}"))
        self.kits_open = False

