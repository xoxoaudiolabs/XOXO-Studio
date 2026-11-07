"""The Studio's XO-4 tab: XO-4's patterns by touch (xo4.py plays them). Mixed into deskui.DeskUI; full screen, as
the decks are: the step grid and the keys need the height the tab bar takes.

  header      < HOME, the patterns A-H (tap: edit it and play it from the next bar; the one playing underlined, one
              waiting outlined), REC (live REC: pads played go onto DRUMS while it plays), PLAY / STOP (the box's
              transport, as the pads' SEQ)
  tracks      DRUMS, SYN 1, SYN 2, MIDI; the track's length (LEN - / +, 1-64); HOLD CLR empties the track here
  steps       16 a page, the playhead lit. DRUMS: a tap puts the pad picked below on the step or takes it off.
              The rest: a tap on an empty step places the last notes there and selects it; a tap on the selected
              step empties it; on another, selects it
  step row    the pages (1-4, as many as the length needs); the selected step's VEL and LEN (in steps) - / +.
              DRUMS: the hit last put on (the pad picked, on that step): its LEVEL (NORM, GHOST, SOFT, HARD), its
              ratchet (X1-X4), the step's NUDGE - / +; QUANT (live REC on the grid, or where it was played)
  below       DRUMS: KIT (the kits: load, save, new), RPT (note repeat), FX (the pads' punch-in FX), PADS (the 16 pads big,
              4x4 as on an MPC, full screen: KIT, RPT, FX, REC, EDIT above them), MIDI IN (off at first: notes from
              the MIDI routes, a synth's or the Pocket's, don't play the pads; on, the routes' SMP column plays the
              track picked here: DRUMS the pads, SYNTH 1 or 2 that synth, a keyboard played live), EDIT,
              and the 16 pads:
              played (they sound while held, playing or not; with REC on, recorded) and picked for the steps; EDIT on,
              a tap opens the pad's page (its sample, level, pan, tune, mode, choke; sampling, trimming). These
              are the pads' own pages (deskpads.py), back to XO-4 when closed. The rest: OCT - / +, KEY and SCALE (the note keys
              offer the scale's notes), FX (XO-4's own punch-in FX, on the two synths' sound), and 14 note keys
              from the octave: a tap adds the note to the selected step
              or takes it off (four at most: a chord); stopped, it sounds. SYN 1 and SYN 2: SOUND opens the synth's
              page (below)

GRID (beside HOLD CLR) shows the whole pattern as XO-4 Pocket does: a row a sound (DRUMS: the pads, 1-8 or 9-16) or
a note of the scale (the rest: OCT - / + moves it), 16 steps across (P 1/2 ... for a longer track), the playhead lit.
A tap puts the row's sound or note on the step or takes it off (four notes a step at most); held, the step is
emptied. The line at the bottom says what's on the step last tapped.

The SOUND page (a synth track's): < XO-4 back, HEAR (its last notes), six starting sounds (KEYS, BASS, BELL,
PLUCK, PAD, LEAD), and the patch's settings, each - / + (held: four steps): RATIO, BRIGHT (the modulation
index), BR DECAY and BR HOLD (how the brightness falls, and what stays), ATTACK, DECAY, SUSTAIN, RELEASE, LEVEL.
While stopped, a change sounds the track's last notes.
"""

import xoxostyle as st

W, H, HDR_H = 480, 320, 34
TRACK_LABELS = ("DRUMS", "SYN 1", "SYN 2", "MIDI")
OCTAVES = (4, 4, 2, 3)                          # the note keys' octave a track starts on (SYN 2: a bass)
KEYS = 14                                       # note keys: two rows of seven
RED = (255, 112, 92)
ROWS = 8                                        # GRID: the rows shown, each a pad or a note
GRID_TOP, ROW_H, LABEL_W, CELL_W = HDR_H + 58, 26, 64, 26   # (the step numbers above the rows)


class DeskXO4:
    def xo4_init(self):
        self.xo4_track = 0                       # the track edited
        self.xo4_edit = None                     # the pattern edited (None: the one playing)
        self.xo4_step = None                     # the selected step (synths, MIDI)
        self.xo4_page = 0
        self.xo4_pad = 0                         # DRUMS: the pad the steps place
        self.xo4_oct = list(OCTAVES)
        self.xo4_brush = [[], [60], [36], [48]]  # the notes a new step gets, a track
        self.xo4_rev = 0                         # bumped with each change: what's drawn follows
        self.xo4_sound = False                   # the SOUND page (SYN 1, SYN 2) open
        self.xo4_rec = False                     # live REC
        self.xo4_grid = False                    # GRID: the whole pattern, a row a pad or a note
        self.xo4_half = 0                        # GRID, DRUMS: pads 1-8 (0) or 9-16 (1)

    # ---- the song

    def xo4_song(self):
        return self.app.song()

    def xo4_pattern(self, song):
        return self.xo4_edit if self.xo4_edit in song["patterns"] else song["pattern"]

    def xo4_save(self, song):
        self.app.set_song(song)
        self.xo4_rev += 1

    def xo4_view(self):
        a = self.app
        x = getattr(a, "xo4", None)
        return (self.xo4_rev, getattr(a, "song_rev", 0), self.xo4_track, self.xo4_edit, self.xo4_step,
                self.xo4_page, self.xo4_pad, tuple(self.xo4_oct), a.seq_playing(), x and x.step, x and x.pattern, x and x.queued, a.clock_text(),
                self.xo4_sound, self.xo4_rec, self.xo4_grid, self.xo4_half,
                self.pads_view() if self.xo4_track == 0 or self.fx_open else None)

    # ---- drawing

    def draw_xo4(self, img, d, now):
        import xo4
        a, t = self.app, self.theme
        song = self.xo4_song()
        if self.fx_open and self.fx_dest == "xo4":
            return self.draw_fx(img, d, now)    # XO-4's synths' FX
        if self.xo4_track == xo4.DRUMS and self.xo4_pad_page():
            return self.draw_pads(img, d, now)  # a pad's page, the kits, sampling, FX: the pads' own
        if self.xo4_sound and self.xo4_track in (xo4.SYNTH1, xo4.SYNTH2):
            return self.draw_xo4_sound(img, d, song)
        name = self.xo4_pattern(song)
        track = song["patterns"][name][self.xo4_track]
        x = getattr(a, "xo4", None)
        playing = a.seq_playing()
        self.button(img, d, (4, 3, 64, HDR_H - 5), "< HOME", lambda: self.open_tab("HOME"), key="xo4-home")
        for k, p in enumerate(xo4.PATTERNS):    # the patterns
            box = (70 + k * 34, 3, 100 + k * 34, HDR_H - 5)
            self.button(img, d, box, p, lambda p=p: self.xo4_pick(p), on=p == name, key=("xo4-pat", p))
            if x and p == (x.pattern or song["pattern"]):
                d.rectangle((box[0], box[3] + 1, box[2], box[3] + 3), fill=t.track[1])
            if x and p == x.queued:
                d.rectangle(box, outline=RED, width=2)
        self.button(img, d, (348, 3, W - 70, HDR_H - 5), "REC", self.xo4_toggle_rec, color=RED, on=self.xo4_rec,
                    key="xo4-rec")
        self.button(img, d, (W - 64, 3, W - 4, HDR_H - 5), "STOP" if playing else "PLAY", a.seq_play, on=playing,
                    key="xo4-play")
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        y = HDR_H + 4                           # the tracks, the length, clear, GRID
        for k, label in enumerate(TRACK_LABELS):
            self.button(img, d, (4 + k * 56, y, 56 + k * 56, y + 32), label, lambda k=k: self.xo4_pick_track(k),
                        color=t.track[k], on=k == self.xo4_track, key=("xo4-track", k))
        self.button(img, d, (W - 56, y, W - 4, y + 32), "GRID", self.xo4_toggle_grid, on=self.xo4_grid,
                    key="xo4-grid")
        if self.xo4_grid:
            return self.draw_xo4_grid(img, d, song, track, x, playing, name)
        self.button(img, d, (232, y, 260, y + 32), "-", lambda: self.xo4_length(-1), key="xo4-len-")
        self.centre(img, (260, y, 316, y + 32), f"LEN {track['len']}", t.hi)
        self.button(img, d, (316, y, 344, y + 32), "+", lambda: self.xo4_length(1), key="xo4-len+")
        self.widget((348, y, W - 60, y + 32), "hold", self.xo4_clear, "xo4-clear")
        d.rectangle((348, y, W - 60, y + 32), fill=t.hi if self.lit("xo4-clear") else t.grey[0])
        self.centre(img, (348, y, W - 60, y + 32), "HOLD CLR", t.bg if self.lit("xo4-clear") else RED)
        self.draw_xo4_steps(img, d, song, name, track, x, playing)
        if self.xo4_track == xo4.DRUMS:
            self.draw_xo4_pads(img, d)
        else:
            self.draw_xo4_keys(img, d, song, track)

    def draw_xo4_steps(self, img, d, song, name, track, x, playing):
        t = self.theme
        pages = (track["len"] + 15) // 16
        self.xo4_page = min(self.xo4_page, pages - 1)
        here = None
        if x and playing and x.step is not None and (x.pattern or song["pattern"]) == name:
            here = x.step % track["len"]
        colour = t.track[self.xo4_track]
        top, sw = HDR_H + 42, W // 16
        for k in range(16):
            idx = self.xo4_page * 16 + k
            box = (k * sw + 1, top, (k + 1) * sw - 2, top + 50)
            if idx >= track["len"]:
                d.rectangle(box, outline=t.c[0])
                continue
            step = track["steps"][idx]
            hit = None
            if self.xo4_track == 0:
                mine = bool(step and self.xo4_pad in step["notes"])
                hit = self.xo4_hit_of(step) if mine else None
            else:
                mine = bool(step)
            fill = t.hi if idx == here else colour if mine else t.grey[1] if k % 4 == 0 else t.grey[0]
            if hit and hit[0] in (1, 2) and idx != here:     # a ghost or soft hit: dimmer
                fill = t.dim[self.xo4_track]
            d.rectangle(box, fill=fill)
            if hit and hit[0] == 3:             # a HARD hit, as the pads' sequencer marks it
                st.text(img, (box[2] - 10, box[1] + 3), "!", t.bg if idx != here else t.c[0])
            if hit and hit[1] > 1:              # ratchet notches
                for r in range(hit[1]):
                    d.rectangle((box[2] - 6 - r * 6, box[1] + 18, box[2] - 3 - r * 6, box[1] + 22), fill=t.bg)
            if step and step.get("nudge"):      # nudged off the grid: a line along the top
                d.line((box[0] + 2, box[1] + 1, box[2] - 2, box[1] + 1), fill=t.track[2], width=2)
            if idx == self.xo4_step:
                d.rectangle(box, outline=t.hi if idx != here else RED, width=2)
            st.text(img, (box[0] + 3, box[1] + 3), str(idx + 1), t.bg if (mine or idx == here) else t.c[2])
            others = len(step["notes"]) - (1 if mine and self.xo4_track == 0 else 0) if step else 0
            for o in range(min(others, 4)):     # the other pads here (DRUMS), or the chord's notes: dots
                d.rectangle((box[0] + 4 + o * 6, box[3] - 8, box[0] + 7 + o * 6, box[3] - 5),
                            fill=t.bg if (mine or idx == here) else t.c[3])
            self.widget(box, "tap", lambda idx=idx: self.xo4_tap(idx), ("xo4-step", idx),
                        lambda idx=idx: self.xo4_clear_step(idx))
        y = top + 56                            # the pages, the selected step's VEL and LEN
        for pg in range(4):
            if pg < pages:
                self.button(img, d, (4 + pg * 38, y, 38 + pg * 38, y + 32), str(pg + 1),
                            lambda pg=pg: self.xo4_go_page(pg), on=pg == self.xo4_page, key=("xo4-page", pg))
        step = track["steps"][self.xo4_step] if self.xo4_step is not None and self.xo4_track else None
        if step:
            for x0, label, value, field, amount in ((160, "VEL", str(step["vel"]), "vel", 8),
                                                    (334, "LEN", f"{step['len']:g}", "len", 0.5)):
                self.button(img, d, (x0, y, x0 + 32, y + 32), "-", lambda f=field, n=amount: self.xo4_change(f, -n),
                            key=("xo4-" + field, "-"))
                self.centre(img, (x0 + 32, y, x0 + 110, y + 32), f"{label} {value}", t.hi)
                self.button(img, d, (x0 + 110, y, x0 + 142, y + 32), "+",
                            lambda f=field, n=amount: self.xo4_change(f, n), key=("xo4-" + field, "+"))
        elif self.xo4_track:
            st.text(img, (164, y + 9), "TAP A STEP, THEN KEYS FOR ITS NOTES", t.c[2])
        else:
            self.draw_xo4_hit(img, d, song, track, y)

    def xo4_grid_rows(self, song):
        """GRID's rows, top to bottom: [(label, pad or note, colour)]"""
        import xo4
        from pathlib import Path
        t = self.theme
        if self.xo4_track == xo4.DRUMS:
            kit = self.app.kit()
            rows = []
            for i in range(self.xo4_half * 8, self.xo4_half * 8 + 8):
                sample = kit["pads"][i]["sample"]
                label = Path(sample).stem.replace("808-", "").replace("-", "")[:7] if sample else f"PAD {i + 1}"
                rows.append((label, i, t.track[(3 - i // 4) % 4]))
            return rows
        low = (self.xo4_oct[self.xo4_track] + 1) * 12 + song["root"]
        return [(xo4.note_name(n), n, t.track[self.xo4_track]) for n in reversed(xo4.scale_notes(song, low, ROWS))]

    def draw_xo4_grid(self, img, d, song, track, x, playing, name):
        """GRID: the pattern's track as rows (pads or notes) by 16 steps, a tap a cell"""
        import xo4
        t = self.theme
        y = HDR_H + 4
        if self.xo4_track == xo4.DRUMS:         # which rows: pads 1-8 or 9-16; the notes an octave at a time
            for h, label in enumerate(("1-8", "9-16")):
                self.button(img, d, (232 + h * 52, y, 280 + h * 52, y + 32), label,
                            lambda h=h: self.xo4_grid_half(h), on=h == self.xo4_half, key=("xo4-half", h))
        else:
            self.button(img, d, (232, y, 260, y + 32), "-", lambda: self.xo4_octave(-1), key="xo4-oct-")
            self.centre(img, (260, y, 316, y + 32), f"OCT {self.xo4_oct[self.xo4_track]}", t.hi)
            self.button(img, d, (316, y, 344, y + 32), "+", lambda: self.xo4_octave(1), key="xo4-oct+")
        pages = (track["len"] + 15) // 16
        self.xo4_page = min(self.xo4_page, pages - 1)
        if pages > 1:
            self.button(img, d, (348, y, W - 60, y + 32), f"P {self.xo4_page + 1}/{pages}",
                        lambda: self.xo4_go_page((self.xo4_page + 1) % pages), key="xo4-grid-page")
        here = None
        if x and playing and x.step is not None and (x.pattern or song["pattern"]) == name:
            here = x.step % track["len"]
        for k in range(16):                     # the step numbers, the beats' first brighter
            idx = self.xo4_page * 16 + k
            if idx < track["len"]:
                st.text(img, (LABEL_W + k * CELL_W + (9 if idx < 9 else 5), GRID_TOP - 18), str(idx + 1),
                        t.hi if idx == here else t.c[3] if k % 4 == 0 else t.c[1])
        drums = self.xo4_track == xo4.DRUMS
        for r, (label, value, colour) in enumerate(self.xo4_grid_rows(song)):
            top = GRID_TOP + r * ROW_H
            picked = drums and value == self.xo4_pad
            st.text(img, (4, top + 5), label, t.hi if picked else colour)
            for k in range(16):
                idx = self.xo4_page * 16 + k
                box = (LABEL_W + k * CELL_W + 1, top + 1, LABEL_W + (k + 1) * CELL_W - 2, top + ROW_H - 2)
                if idx >= track["len"]:
                    d.rectangle(box, outline=t.c[0])
                    continue
                step = track["steps"][idx]
                on = bool(step and value in step["notes"])
                if on:
                    fill = t.hi if idx == here else colour
                    if drums:                   # a ghost or soft hit: dimmer
                        level = (step.get("levels") or [0] * len(step["notes"]))[step["notes"].index(value)]
                        fill = t.dim[0] if level in (1, 2) and idx != here else fill
                else:
                    fill = t.c[1] if idx == here else t.grey[1] if k // 4 % 2 == 0 else t.grey[0]
                d.rectangle(box, fill=fill)
                if idx == self.xo4_step and on:
                    d.rectangle(box, outline=t.hi if idx != here else RED, width=2)
                self.widget(box, "tap", lambda idx=idx, v=value: self.xo4_grid_tap(idx, v), ("xo4-cell", idx, value),
                            lambda idx=idx: self.xo4_clear_step(idx))
        st.text(img, (4, H - 17), self.xo4_grid_status(song, track), t.c[3])

    def xo4_grid_status(self, song, track):
        """GRID's bottom line: the step last tapped, or what a tap does"""
        import xo4
        step = track["steps"][self.xo4_step] if self.xo4_step is not None else None
        if not step:
            return "TAP: ON / OFF   HOLD: EMPTY THE STEP"
        if self.xo4_track == xo4.DRUMS:
            hit = self.xo4_hit_of(step)
            if not hit:
                return f"STEP {self.xo4_step + 1}"
            return (f"STEP {self.xo4_step + 1}  PAD {self.xo4_pad + 1}  {xo4.LEVELS[hit[0]]}  X{hit[1]}  "
                    f"NUDGE {step.get('nudge', 0):+d}")
        notes = " ".join(xo4.note_name(n) for n in step["notes"])
        return f"STEP {self.xo4_step + 1}  {notes}  VEL {step['vel']}  LEN {step['len']:g}"

    def xo4_hit_of(self, step):
        """(level, ratchet) of the pad picked on this drum step, or None"""
        if not step or self.xo4_pad not in step["notes"]:
            return None
        k = step["notes"].index(self.xo4_pad)
        return (step.get("levels") or [0] * len(step["notes"]))[k], (step.get("ratchets") or [1] * len(step["notes"]))[k]

    def draw_xo4_hit(self, img, d, song, track, y):
        """DRUMS' step row: the selected hit's LEVEL, ratchet and the step's NUDGE; QUANT"""
        import xo4
        t = self.theme
        step = track["steps"][self.xo4_step] if self.xo4_step is not None else None
        hit = self.xo4_hit_of(step)
        if hit:
            self.button(img, d, (158, y, 228, y + 32), xo4.LEVELS[hit[0]], self.xo4_hit_level, key="xo4-level")
            self.button(img, d, (234, y, 280, y + 32), f"X{hit[1]}", self.xo4_hit_ratchet, key="xo4-ratchet")
            self.button(img, d, (286, y, 316, y + 32), "-", lambda: self.xo4_nudge(-4), key="xo4-nudge-")
            self.centre(img, (316, y, 372, y + 32), f"{step.get('nudge', 0):+d}", t.hi)
            self.button(img, d, (372, y, 402, y + 32), "+", lambda: self.xo4_nudge(4), key="xo4-nudge+")
        else:
            st.text(img, (164, y + 9), f"STEPS PUT PAD {self.xo4_pad + 1} ON / OFF", t.c[2])
        self.button(img, d, (408, y, W - 4, y + 32), "Q ON" if song["quant"] else "Q OFF", self.xo4_quant,
                    on=song["quant"], key="xo4-quant")

    def xo4_pad_page(self):
        """a pads' page open over XO-4's DRUMS"""
        return (self.pad_edit is not None or self.kits_open or self.pad_rec is not None
                or self.pad_pick_source is not None or self.fx_open or self.mpc_open)

    def draw_xo4_pads(self, img, d):
        import pads
        a, t = self.app, self.theme
        kit = a.kit()
        y = HDR_H + 136                         # KIT, RPT, FX, EDIT (where the synths have OCT, KEY, SCALE, SOUND)
        repeat = a.state.get("repeat")
        self.button(img, d, (4, y, 96, y + 30), kit["name"][:10], self.open_kits, key="xo4-kits")
        self.button(img, d, (100, y, 182, y + 30), "RPT" if repeat is None else "RPT " + pads.DIVS[repeat],
                    self.toggle_repeat, on=repeat is not None, key="xo4-rpt")
        self.button(img, d, (186, y, 226, y + 30), "FX", self.open_fx, on=self.fx_on is not None, key="xo4-fx")
        self.button(img, d, (230, y, 290, y + 30), "PADS", self.open_mpc, key="xo4-mpc")   # the big pads
        self.button(img, d, (294, y, 384, y + 30), "MIDI IN", self.xo4_toggle_midi_in,
                    on=bool(a.state.get("xo4_midi_in")), key="xo4-midi-in")
        self.button(img, d, (388, y, W - 4, y + 30), "EDIT", self.toggle_pad_mode, on=self.pad_mode, key="xo4-edit")
        top, pw = y + 36, W // 8
        sounding = set(a.pads.sounding) if a.pads else set()
        for i in range(16):
            r = 1 - i // 8                      # pads 1-8 the bottom row, as on an MPC
            box = (i % 8 * pw + 2, top + r * 54, (i % 8 + 1) * pw - 3, top + r * 54 + 50)
            colour = t.track[(3 - i // 4) % 4]
            on = i == self.xo4_pad
            lit = i in sounding or self.lit(("xo4-pad", i))
            d.rectangle(box, fill=t.hi if lit else colour if on else t.grey[0], outline=colour, width=2)
            st.text(img, (box[0] + 5, box[1] + 4), str(i + 1), t.bg if (on or lit) else colour)
            sample = kit["pads"][i]["sample"]
            if sample:
                from pathlib import Path
                st.text(img, (box[0] + 5, box[3] - 18), Path(sample).stem.replace("808-", "").replace("-", "")[:6],
                        t.bg if (on or lit) else t.c[3])
            if self.pad_mode:                   # EDIT: the pad's page
                self.widget(box, "tap", lambda i=i: self.open_pad(i), ("xo4-pad", i))
            else:                               # played while held, and picked for the steps
                self.widget(box, "gate", lambda down, i=i: self.xo4_play_pad(i, down), ("xo4-pad", i))

    def draw_xo4_keys(self, img, d, song, track):
        import xo4
        t = self.theme
        y = HDR_H + 136
        octave = self.xo4_oct[self.xo4_track]
        self.button(img, d, (4, y, 36, y + 30), "-", lambda: self.xo4_octave(-1), key="xo4-oct-")
        self.centre(img, (36, y, 100, y + 30), f"OCT {octave}", t.hi)
        self.button(img, d, (100, y, 132, y + 30), "+", lambda: self.xo4_octave(1), key="xo4-oct+")
        self.button(img, d, (140, y, 228, y + 30), "KEY " + xo4.NOTE_NAMES[song["root"]], self.xo4_root,
                    key="xo4-root")
        self.button(img, d, (232, y, 338, y + 30), song["scale"], self.xo4_scale, key="xo4-scale")
        if self.xo4_track == xo4.MIDI:
            st.text(img, (388, y + 8), f"CH {song['midi_channel'] + 1}", t.c[3])
        else:                                   # a synth: XO-4's synths' FX, and its SOUND page
            self.button(img, d, (342, y, 402, y + 30), "FX", lambda: self.open_fx("xo4"),
                        on=self.xo4_fx[0] is not None, key="xo4-synth-fx")
            self.button(img, d, (406, y, W - 4, y + 30), "SOUND", self.xo4_sound_open, color=t.track[self.xo4_track],
                        key="xo4-sound")
        step = track["steps"][self.xo4_step] if self.xo4_step is not None else None
        held = set(step["notes"]) if step else set()
        low = (octave + 1) * 12 + song["root"]
        notes = xo4.scale_notes(song, low, KEYS)
        kw = W // 7
        for k, note in enumerate(notes):
            box = (k % 7 * kw + 2, y + 36 + k // 7 * 56, (k % 7 + 1) * kw - 3, y + 36 + k // 7 * 56 + 50)
            on = note in held
            root = (note - song["root"]) % 12 == 0
            d.rectangle(box, fill=t.track[self.xo4_track] if on else t.grey[1] if root else t.grey[0])
            self.centre(img, box, xo4.note_name(note), t.bg if on else t.hi)
            self.widget(box, "tap", lambda n=note: self.xo4_key(n), ("xo4-key", note))

    # ---- what the taps do

    def xo4_pick(self, p):
        """a pattern: edited from now, played from the next bar (at once while stopped)"""
        self.xo4_edit, self.xo4_step, self.xo4_page = p, None, 0
        self.app.xo4_pick_pattern(p)
        self.xo4_rev += 1

    def xo4_pick_track(self, k):
        self.xo4_track, self.xo4_step, self.xo4_page, self.xo4_sound = k, None, 0, False
        if hasattr(self.app, "set_xo4_keys"):   # MIDI IN plays the track picked (the MIDI track: as it was)
            self.app.set_xo4_keys(k)
        self.xo4_rev += 1

    def xo4_play_pad(self, i, down):
        """a pad touched: it sounds while held (playing or not: with REC on, XO-4 records it), and is the one the
        steps place"""
        if down and self.xo4_pad != i:
            self.xo4_pad = i
            self.xo4_rev += 1
        self.hit(i, down)

    def xo4_go_page(self, pg):
        self.xo4_page = pg
        self.xo4_rev += 1

    def xo4_track_of(self, song):
        return song["patterns"][self.xo4_pattern(song)][self.xo4_track]

    def xo4_tap(self, idx):
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        step = track["steps"][idx]
        if self.xo4_track == 0:                 # DRUMS: the pad picked, on or off (the others' hits kept)
            n = len(step["notes"]) if step else 0
            hits = {p: (lv, r) for p, lv, r in zip(step["notes"] if step else [], (step or {}).get("levels") or [0] * n,
                                                   (step or {}).get("ratchets") or [1] * n)}
            if self.xo4_pad in hits:
                del hits[self.xo4_pad]
                self.xo4_step = None if self.xo4_step == idx else self.xo4_step
            else:
                hits[self.xo4_pad] = (0, 1)
                self.xo4_step = idx             # the hit just put on: its LEVEL, ratchet, NUDGE below
            pads = sorted(hits)
            track["steps"][idx] = dict(step or {"vel": 100, "len": 1.0, "nudge": 0}, notes=pads,
                                       levels=[hits[p][0] for p in pads], ratchets=[hits[p][1] for p in pads]) \
                if pads else None
        elif not step:                          # an empty step: the last notes, selected
            track["steps"][idx] = {"notes": list(self.xo4_brush[self.xo4_track] or [60]), "vel": 100, "len": 1.0}
            self.xo4_step = idx
            self.xo4_audition(track["steps"][idx]["notes"])
        elif idx == self.xo4_step:              # the selected one again: emptied
            track["steps"][idx], self.xo4_step = None, None
        else:
            self.xo4_step = idx
            self.xo4_audition(step["notes"])
        self.xo4_save(song)

    def xo4_toggle_grid(self):
        self.xo4_grid = not self.xo4_grid
        self.xo4_rev += 1

    def xo4_grid_half(self, h):
        self.xo4_half = h
        self.xo4_rev += 1

    def xo4_grid_tap(self, idx, value):
        """a GRID cell: DRUMS, its pad on the step or off (and picked); the rest, its note on or off the step"""
        if self.xo4_track == 0:
            self.xo4_pad = value
            return self.xo4_tap(idx)
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        step = track["steps"][idx]
        if not step:
            track["steps"][idx] = {"notes": [value], "vel": 100, "len": 1.0}
            self.xo4_audition([value])
        elif value in step["notes"]:
            if len(step["notes"]) == 1:         # its last note: the step emptied
                track["steps"][idx] = None
                self.xo4_step = None if self.xo4_step == idx else self.xo4_step
                return self.xo4_save(song)
            step["notes"] = [n for n in step["notes"] if n != value]
        elif len(step["notes"]) >= 4:
            self.app.say("Four notes a step at most", 2)
            return
        else:
            step["notes"] = sorted(step["notes"] + [value])
            self.xo4_audition([value])
        self.xo4_step = idx
        self.xo4_brush[self.xo4_track] = list(track["steps"][idx]["notes"])
        self.xo4_save(song)

    def xo4_hit_change(self, change):
        """the selected drum hit (the pad picked, on the selected step) changed by change(levels, ratchets, k)"""
        song = self.xo4_song()
        step = self.xo4_track_of(song)["steps"][self.xo4_step] if self.xo4_step is not None else None
        if not step or self.xo4_pad not in step["notes"]:
            return
        n = len(step["notes"])
        step["levels"] = list(step.get("levels") or [0] * n)
        step["ratchets"] = list(step.get("ratchets") or [1] * n)
        change(step["levels"], step["ratchets"], step["notes"].index(self.xo4_pad))
        self.xo4_save(song)

    def xo4_hit_level(self):
        """NORM, HARD, GHOST, SOFT round (the pads' order: louder first, then the quiet ones)"""
        order = [0, 3, 1, 2]
        self.xo4_hit_change(lambda lv, r, k: lv.__setitem__(k, order[(order.index(lv[k]) + 1) % 4]))

    def xo4_hit_ratchet(self):
        self.xo4_hit_change(lambda lv, r, k: r.__setitem__(k, r[k] % 4 + 1))

    def xo4_nudge(self, amount):
        song = self.xo4_song()
        step = self.xo4_track_of(song)["steps"][self.xo4_step] if self.xo4_step is not None else None
        if step:
            step["nudge"] = max(-32, min(31, step.get("nudge", 0) + amount))
            self.xo4_save(song)

    def xo4_quant(self):
        song = self.xo4_song()
        song["quant"] = not song["quant"]
        self.xo4_save(song)

    def xo4_toggle_midi_in(self):
        """MIDI IN: the routes' notes play the track picked (on: the pads, or SYNTH 1 / 2) or not (off: a synth on
        the routes plays only itself)"""
        self.app.set_xo4_midi_in(not self.app.state.get("xo4_midi_in"))
        self.xo4_rev += 1

    def xo4_toggle_rec(self):
        self.xo4_rec = not self.xo4_rec
        x = getattr(self.app, "xo4", None)
        if x:
            x.send("rec", self.xo4_rec)
        self.xo4_rev += 1

    def xo4_clear_step(self, idx):
        """a step held: emptied (DRUMS: every pad on it)"""
        song = self.xo4_song()
        self.xo4_track_of(song)["steps"][idx] = None
        if self.xo4_step == idx:
            self.xo4_step = None
        self.xo4_save(song)

    def xo4_key(self, note):
        """a note key: on the selected step or off it (four at most); none selected: just heard"""
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        step = track["steps"][self.xo4_step] if self.xo4_step is not None else None
        self.xo4_audition([note])
        if not step:
            self.xo4_brush[self.xo4_track] = [note]
            self.xo4_rev += 1
            return
        notes = list(step["notes"])
        if note in notes:
            if len(notes) == 1:
                self.app.say("A step keeps one note: tap the step to empty it", 2)
                return
            notes.remove(note)
        elif len(notes) >= 4:
            self.app.say("Four notes a step at most", 2)
            return
        else:
            notes.append(note)
        step["notes"] = sorted(notes)
        self.xo4_brush[self.xo4_track] = list(step["notes"])
        self.xo4_save(song)

    def xo4_audition(self, notes):
        x = getattr(self.app, "xo4", None)
        if x and self.xo4_track in (1, 2) and not self.app.seq_playing():
            x.send("audition", self.xo4_track, list(notes), 100)

    def xo4_change(self, field, amount):
        song = self.xo4_song()
        step = self.xo4_track_of(song)["steps"][self.xo4_step] if self.xo4_step is not None else None
        if not step:
            return
        if field == "vel":
            step["vel"] = max(1, min(127, step["vel"] + amount))
        else:
            step["len"] = max(0.5, min(16.0, step["len"] + amount))
        self.xo4_save(song)

    def xo4_length(self, step):
        import xo4
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        track["len"] = max(1, min(xo4.NSTEP, track["len"] + step))
        if self.xo4_step is not None and self.xo4_step >= track["len"]:
            self.xo4_step = None
        self.xo4_save(song)

    def xo4_clear(self):
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        track["steps"] = [None] * len(track["steps"])
        self.xo4_step = None
        self.xo4_save(song)
        self.app.say(f"{TRACK_LABELS[self.xo4_track]} cleared in {self.xo4_pattern(song)}", 2)

    def xo4_octave(self, step):
        self.xo4_oct[self.xo4_track] = max(0, min(8, self.xo4_oct[self.xo4_track] + step))
        self.xo4_rev += 1

    def xo4_root(self):
        song = self.xo4_song()
        song["root"] = (song["root"] + 1) % 12
        self.xo4_save(song)

    # ---- the SOUND page

    def draw_xo4_sound(self, img, d, song):
        import xo4
        import xo4synth
        t = self.theme
        k = self.xo4_track
        patch = song["patches"][k - xo4.SYNTH1]
        self.button(img, d, (4, 3, 80, HDR_H - 5), "< XO-4", self.xo4_sound_close, key="xo4-sound-back")
        st.text(img, (90, 9), f"{TRACK_LABELS[k]} SOUND", t.track[k])
        self.button(img, d, (W - 84, 3, W - 4, HDR_H - 5), "HEAR", self.xo4_hear, key="xo4-hear")
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        names = list(xo4.SOUNDS)                # the starting sounds; the one the patch is now lit
        bw = (W - 8) // len(names)
        for n, name in enumerate(names):
            same = xo4synth.clean_patch(xo4.SOUNDS[name]) == patch
            self.button(img, d, (4 + n * bw, HDR_H + 4, 4 + (n + 1) * bw - 4, HDR_H + 36), name,
                        lambda name=name: self.xo4_sound_preset(name), color=t.track[k], on=same,
                        key=("xo4-preset", name))
        left = ("ratio", "index", "mod_decay", "mod_sustain", "level")
        right = ("attack", "decay", "sustain", "release")
        names = {key: label for key, label, _ in xo4.SETTINGS}
        for col, keys in enumerate((left, right)):
            for row, key in enumerate(keys):
                x0, y = 4 + col * 238, HDR_H + 42 + row * 48
                self.button(img, d, (x0, y, x0 + 44, y + 42), "-", lambda key=key: self.xo4_sound_set(key, -1),
                            key=("xo4-set", key, "-"), long=lambda key=key: self.xo4_sound_set(key, -4))
                d.rectangle((x0 + 48, y, x0 + 182, y + 42), fill=t.grey[0])
                self.centre(img, (x0 + 48, y + 2, x0 + 182, y + 20), names[key], t.c[2])
                self.centre(img, (x0 + 48, y + 20, x0 + 182, y + 40), xo4.setting_text(key, patch[key]), t.hi)
                self.button(img, d, (x0 + 186, y, x0 + 230, y + 42), "+", lambda key=key: self.xo4_sound_set(key, 1),
                            key=("xo4-set", key, "+"), long=lambda key=key: self.xo4_sound_set(key, 4))

    def xo4_sound_open(self):
        self.xo4_sound = True
        self.xo4_rev += 1

    def xo4_sound_close(self):
        self.xo4_sound = False
        self.xo4_rev += 1

    def xo4_patch_change(self, change):
        """the synth track's patch changed by change(patch); kept, sent to XO-4, and (stopped) heard"""
        import xo4
        song = self.xo4_song()
        patch = song["patches"][self.xo4_track - xo4.SYNTH1]
        change(patch)
        self.xo4_save(song)
        if not self.app.seq_playing():
            self.xo4_hear()

    def xo4_sound_set(self, key, steps):
        import xo4
        self.xo4_patch_change(lambda patch: patch.__setitem__(key, xo4.step_setting(key, patch[key], steps)))

    def xo4_sound_preset(self, name):
        import xo4
        self.xo4_patch_change(lambda patch: patch.update(xo4.SOUNDS[name]))

    def xo4_hear(self):
        """the track's last notes, heard now (playing or not)"""
        x = getattr(self.app, "xo4", None)
        if x and self.xo4_track in (1, 2):
            x.send("audition", self.xo4_track, list(self.xo4_brush[self.xo4_track] or [60]), 100)

    def xo4_scale(self):
        import xo4
        song = self.xo4_song()
        names = list(xo4.SCALES)
        song["scale"] = names[(names.index(song["scale"]) + 1) % len(names)]
        self.xo4_save(song)
