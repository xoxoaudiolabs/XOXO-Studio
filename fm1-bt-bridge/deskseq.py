"""The Studio's SEQ tab: the sequencer's eight MIDI tracks by touch (sequencer.py plays them). Mixed into
deskui.DeskUI; full screen: the step grid and the keys need the height the tab bar takes.

  header      < HOME, the patterns A-H (tap: edit it and play it from the next bar; the one playing underlined, one
              waiting outlined), PLAY / STOP (the box's transport)
  tracks      1-8; the track's length (LEN - / +, 1-64); HOLD CLR empties the track here; GRID
  steps       16 a page (four pages: 64 steps), the playhead lit. A tap on an empty step places the last notes there
              and selects it; a tap on the selected step empties it; on another, selects it; held, it's emptied
  step row    the pages (1-4, as many as the length needs); the selected step's VEL and LEN (in steps) - / +
  below       OCT - / +, KEY and SCALE (the note keys offer the scale's notes), CH (the track's MIDI channel: a tap
              the next, held the one before), and 14 note keys from the octave: a tap adds the note to the selected
              step or takes it off (four at most: a chord)

GRID (beside HOLD CLR) shows the whole pattern's track: a row a note of the scale (OCT - / + moves it), 16 steps
across (P 1/2 ... for a longer track), the playhead lit. A tap puts the row's note on the step or takes it off (four
notes a step at most); held, the step is emptied. The line at the bottom says what's on the step last tapped.

The pads (the sampler plug-in) aren't on this screen: they play from SEQ as MIDI gear does, through the route
SEQ > SMP (notes 36-51).
"""

import xoxostyle as st

W, H, HDR_H = 480, 320, 34
NTRACK = 8
KEYS = 14                                       # note keys: two rows of seven
RED = (255, 112, 92)
ROWS = 8                                        # GRID: the rows shown, each a note
GRID_TOP, ROW_H, LABEL_W, CELL_W = HDR_H + 58, 26, 64, 26   # (the step numbers above the rows)


class DeskSeq:
    def sq_init(self):
        self.sq_track = 0                       # the track edited (0-7)
        self.sq_edit = None                     # the pattern edited (None: the one playing)
        self.sq_step = None                     # the selected step
        self.sq_page = 0
        self.sq_oct = [4] * NTRACK              # the note keys' octave, a track
        self.sq_brush = [[60] for _ in range(NTRACK)]   # the notes a new step gets, a track
        self.sq_rev = 0                         # bumped with each change: what's drawn follows
        self.sq_grid = False                    # GRID: the whole pattern, a row a note

    # ---- the song

    def sq_song(self):
        return self.app.song()

    def sq_pattern(self, song):
        return self.sq_edit if self.sq_edit in song["patterns"] else song["pattern"]

    def sq_save(self, song):
        self.app.set_song(song)
        self.sq_rev += 1

    def sq_view(self):
        a = self.app
        x = getattr(a, "sequencer", None)
        return (self.sq_rev, getattr(a, "song_rev", 0), self.sq_track, self.sq_edit, self.sq_step, self.sq_page,
                tuple(self.sq_oct), a.seq_playing(), x and x.step, x and x.pattern, x and x.queued, a.clock_text(),
                self.sq_grid)

    def sq_track_of(self, song):
        return song["patterns"][self.sq_pattern(song)][self.sq_track]

    # ---- drawing

    def draw_sq(self, img, d, now):
        import sequencer
        a, t = self.app, self.theme
        song = self.sq_song()
        name = self.sq_pattern(song)
        track = song["patterns"][name][self.sq_track]
        x = getattr(a, "sequencer", None)
        playing = a.seq_playing()
        self.button(img, d, (4, 3, 64, HDR_H - 5), "< HOME", lambda: self.open_tab("HOME"), key="seq-home")
        for k, p in enumerate(sequencer.PATTERNS):    # the patterns
            box = (70 + k * 34, 3, 100 + k * 34, HDR_H - 5)
            self.button(img, d, box, p, lambda p=p: self.sq_pick(p), on=p == name, key=("seq-pat", p))
            if x and p == (x.pattern or song["pattern"]):
                d.rectangle((box[0], box[3] + 1, box[2], box[3] + 3), fill=t.track[1])
            if x and p == x.queued:
                d.rectangle(box, outline=RED, width=2)
        self.button(img, d, (348, 3, W - 4, HDR_H - 5), "STOP" if playing else "PLAY", a.seq_play, on=playing,
                    key="seq-play")
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        y = HDR_H + 4                           # the tracks, the length, clear, GRID
        for k in range(NTRACK):
            self.button(img, d, (4 + k * 28, y, 29 + k * 28, y + 32), str(k + 1),
                        lambda k=k: self.sq_pick_track(k), color=t.track[3], on=k == self.sq_track,
                        key=("seq-track", k))
        self.button(img, d, (W - 56, y, W - 4, y + 32), "GRID", self.sq_toggle_grid, on=self.sq_grid,
                    key="seq-grid")
        if self.sq_grid:
            return self.draw_sq_grid(img, d, song, track, x, playing, name)
        self.button(img, d, (232, y, 260, y + 32), "-", lambda: self.sq_length(-1), key="seq-len-")
        self.centre(img, (260, y, 316, y + 32), f"LEN {track['len']}", t.hi)
        self.button(img, d, (316, y, 344, y + 32), "+", lambda: self.sq_length(1), key="seq-len+")
        self.widget((348, y, W - 60, y + 32), "hold", self.sq_clear, "seq-clear")
        d.rectangle((348, y, W - 60, y + 32), fill=t.hi if self.lit("seq-clear") else t.grey[0])
        self.centre(img, (348, y, W - 60, y + 32), "HOLD CLR", t.bg if self.lit("seq-clear") else RED)
        self.draw_sq_steps(img, d, song, name, track, x, playing)
        self.draw_sq_keys(img, d, song, track)

    def draw_sq_steps(self, img, d, song, name, track, x, playing):
        t = self.theme
        pages = (track["len"] + 15) // 16
        self.sq_page = min(self.sq_page, pages - 1)
        here = None
        if x and playing and x.step is not None and (x.pattern or song["pattern"]) == name:
            here = x.step % track["len"]
        colour = t.track[3]
        top, sw = HDR_H + 42, W // 16
        for k in range(16):
            idx = self.sq_page * 16 + k
            box = (k * sw + 1, top, (k + 1) * sw - 2, top + 50)
            if idx >= track["len"]:
                d.rectangle(box, outline=t.c[0])
                continue
            step = track["steps"][idx]
            mine = bool(step)
            fill = t.hi if idx == here else colour if mine else t.grey[1] if k % 4 == 0 else t.grey[0]
            d.rectangle(box, fill=fill)
            if step and step.get("nudge"):      # nudged off the grid: a line along the top
                d.line((box[0] + 2, box[1] + 1, box[2] - 2, box[1] + 1), fill=t.track[2], width=2)
            if idx == self.sq_step:
                d.rectangle(box, outline=t.hi if idx != here else RED, width=2)
            st.text(img, (box[0] + 3, box[1] + 3), str(idx + 1), t.bg if (mine or idx == here) else t.c[2])
            for o in range(min(len(step["notes"]) if step else 0, 4)):   # the chord's notes: dots
                d.rectangle((box[0] + 4 + o * 6, box[3] - 8, box[0] + 7 + o * 6, box[3] - 5),
                            fill=t.bg if (mine or idx == here) else t.c[3])
            self.widget(box, "tap", lambda idx=idx: self.sq_tap(idx), ("seq-step", idx),
                        lambda idx=idx: self.sq_clear_step(idx))
        y = top + 56                            # the pages, the selected step's VEL and LEN
        for pg in range(4):
            if pg < pages:
                self.button(img, d, (4 + pg * 38, y, 38 + pg * 38, y + 32), str(pg + 1),
                            lambda pg=pg: self.sq_go_page(pg), on=pg == self.sq_page, key=("seq-page", pg))
        step = track["steps"][self.sq_step] if self.sq_step is not None else None
        if step:
            for x0, label, value, field, amount in ((160, "VEL", str(step["vel"]), "vel", 8),
                                                    (334, "LEN", f"{step['len']:g}", "len", 0.5)):
                self.button(img, d, (x0, y, x0 + 32, y + 32), "-", lambda f=field, n=amount: self.sq_change(f, -n),
                            key=("seq-" + field, "-"))
                self.centre(img, (x0 + 32, y, x0 + 110, y + 32), f"{label} {value}", t.hi)
                self.button(img, d, (x0 + 110, y, x0 + 142, y + 32), "+",
                            lambda f=field, n=amount: self.sq_change(f, n), key=("seq-" + field, "+"))
        else:
            st.text(img, (164, y + 9), "TAP A STEP, THEN KEYS FOR ITS NOTES", t.c[2])

    def sq_grid_rows(self, song):
        """GRID's rows, top to bottom: [(label, note)]"""
        import sequencer
        low = (self.sq_oct[self.sq_track] + 1) * 12 + song["root"]
        return [(sequencer.note_name(n), n) for n in reversed(sequencer.scale_notes(song, low, ROWS))]

    def draw_sq_grid(self, img, d, song, track, x, playing, name):
        """GRID: the pattern's track as rows of notes by 16 steps, a tap a cell"""
        t = self.theme
        y = HDR_H + 4
        self.button(img, d, (232, y, 260, y + 32), "-", lambda: self.sq_octave(-1), key="seq-oct-")
        self.centre(img, (260, y, 316, y + 32), f"OCT {self.sq_oct[self.sq_track]}", t.hi)
        self.button(img, d, (316, y, 344, y + 32), "+", lambda: self.sq_octave(1), key="seq-oct+")
        pages = (track["len"] + 15) // 16
        self.sq_page = min(self.sq_page, pages - 1)
        if pages > 1:
            self.button(img, d, (348, y, W - 60, y + 32), f"P {self.sq_page + 1}/{pages}",
                        lambda: self.sq_go_page((self.sq_page + 1) % pages), key="seq-grid-page")
        here = None
        if x and playing and x.step is not None and (x.pattern or song["pattern"]) == name:
            here = x.step % track["len"]
        for k in range(16):                     # the step numbers, the beats' first brighter
            idx = self.sq_page * 16 + k
            if idx < track["len"]:
                st.text(img, (LABEL_W + k * CELL_W + (9 if idx < 9 else 5), GRID_TOP - 18), str(idx + 1),
                        t.hi if idx == here else t.c[3] if k % 4 == 0 else t.c[1])
        colour = t.track[3]
        for r, (label, value) in enumerate(self.sq_grid_rows(song)):
            top = GRID_TOP + r * ROW_H
            st.text(img, (4, top + 5), label, colour)
            for k in range(16):
                idx = self.sq_page * 16 + k
                box = (LABEL_W + k * CELL_W + 1, top + 1, LABEL_W + (k + 1) * CELL_W - 2, top + ROW_H - 2)
                if idx >= track["len"]:
                    d.rectangle(box, outline=t.c[0])
                    continue
                step = track["steps"][idx]
                on = bool(step and value in step["notes"])
                if on:
                    fill = t.hi if idx == here else colour
                else:
                    fill = t.c[1] if idx == here else t.grey[1] if k // 4 % 2 == 0 else t.grey[0]
                d.rectangle(box, fill=fill)
                if idx == self.sq_step and on:
                    d.rectangle(box, outline=t.hi if idx != here else RED, width=2)
                self.widget(box, "tap", lambda idx=idx, v=value: self.sq_grid_tap(idx, v), ("seq-cell", idx, value),
                            lambda idx=idx: self.sq_clear_step(idx))
        st.text(img, (4, H - 17), self.sq_grid_status(song, track), t.c[3])

    def sq_grid_status(self, song, track):
        """GRID's bottom line: the step last tapped, or what a tap does"""
        import sequencer
        step = track["steps"][self.sq_step] if self.sq_step is not None else None
        if not step:
            return "TAP: ON / OFF   HOLD: EMPTY THE STEP"
        notes = " ".join(sequencer.note_name(n) for n in step["notes"])
        return f"STEP {self.sq_step + 1}  {notes}  VEL {step['vel']}  LEN {step['len']:g}"

    def draw_sq_keys(self, img, d, song, track):
        import sequencer
        t = self.theme
        y = HDR_H + 136
        octave = self.sq_oct[self.sq_track]
        self.button(img, d, (4, y, 36, y + 30), "-", lambda: self.sq_octave(-1), key="seq-oct-")
        self.centre(img, (36, y, 100, y + 30), f"OCT {octave}", t.hi)
        self.button(img, d, (100, y, 132, y + 30), "+", lambda: self.sq_octave(1), key="seq-oct+")
        self.button(img, d, (140, y, 228, y + 30), "KEY " + sequencer.NOTE_NAMES[song["root"]], self.sq_root,
                    key="seq-root")
        self.button(img, d, (232, y, 338, y + 30), song["scale"], self.sq_scale, key="seq-scale")
        self.button(img, d, (342, y, W - 4, y + 30), f"CH {song['tracks'][self.sq_track]['channel'] + 1}",
                    lambda: self.sq_channel(1), color=t.track[3], key="seq-channel",
                    long=lambda: self.sq_channel(-1))
        step = track["steps"][self.sq_step] if self.sq_step is not None else None
        held = set(step["notes"]) if step else set()
        low = (octave + 1) * 12 + song["root"]
        notes = sequencer.scale_notes(song, low, KEYS)
        kw = W // 7
        for k, note in enumerate(notes):
            box = (k % 7 * kw + 2, y + 36 + k // 7 * 56, (k % 7 + 1) * kw - 3, y + 36 + k // 7 * 56 + 50)
            on = note in held
            root = (note - song["root"]) % 12 == 0
            d.rectangle(box, fill=t.track[3] if on else t.grey[1] if root else t.grey[0])
            self.centre(img, box, sequencer.note_name(note), t.bg if on else t.hi)
            self.widget(box, "tap", lambda n=note: self.sq_key(n), ("seq-key", note))

    # ---- what the taps do

    def sq_pick(self, p):
        """a pattern: edited from now, played from the next bar (at once while stopped)"""
        self.sq_edit, self.sq_step, self.sq_page = p, None, 0
        self.app.sq_pick_pattern(p)
        self.sq_rev += 1

    def sq_pick_track(self, k):
        if 0 <= k < NTRACK:
            self.sq_track, self.sq_step, self.sq_page = k, None, 0
            self.sq_rev += 1

    def sq_channel(self, step):
        """the track's MIDI channel: the next (or the one before), 1-16 round"""
        song = self.sq_song()
        t = song["tracks"][self.sq_track]
        t["channel"] = (t["channel"] + step) % 16
        self.sq_save(song)

    def sq_go_page(self, pg):
        self.sq_page = pg
        self.sq_rev += 1

    def sq_tap(self, idx):
        song = self.sq_song()
        track = self.sq_track_of(song)
        step = track["steps"][idx]
        if not step:                            # an empty step: the last notes, selected
            track["steps"][idx] = {"notes": list(self.sq_brush[self.sq_track] or [60]), "vel": 100, "len": 1.0}
            self.sq_step = idx
        elif idx == self.sq_step:              # the selected one again: emptied
            track["steps"][idx], self.sq_step = None, None
        else:
            self.sq_step = idx
        self.sq_save(song)

    def sq_toggle_grid(self):
        self.sq_grid = not self.sq_grid
        self.sq_rev += 1

    def sq_grid_tap(self, idx, value):
        """a GRID cell: its note on the step or off"""
        song = self.sq_song()
        track = self.sq_track_of(song)
        step = track["steps"][idx]
        if not step:
            track["steps"][idx] = {"notes": [value], "vel": 100, "len": 1.0}
        elif value in step["notes"]:
            if len(step["notes"]) == 1:         # its last note: the step emptied
                track["steps"][idx] = None
                self.sq_step = None if self.sq_step == idx else self.sq_step
                return self.sq_save(song)
            step["notes"] = [n for n in step["notes"] if n != value]
        elif len(step["notes"]) >= 4:
            self.app.say("Four notes a step at most", 2)
            return
        else:
            step["notes"] = sorted(step["notes"] + [value])
        self.sq_step = idx
        self.sq_brush[self.sq_track] = list(track["steps"][idx]["notes"])
        self.sq_save(song)

    def sq_clear_step(self, idx):
        """a step held: emptied"""
        song = self.sq_song()
        self.sq_track_of(song)["steps"][idx] = None
        if self.sq_step == idx:
            self.sq_step = None
        self.sq_save(song)

    def sq_key(self, note):
        """a note key: on the selected step or off it (four at most); none selected: the notes a new step gets"""
        song = self.sq_song()
        track = self.sq_track_of(song)
        step = track["steps"][self.sq_step] if self.sq_step is not None else None
        if not step:
            self.sq_brush[self.sq_track] = [note]
            self.sq_rev += 1
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
        self.sq_brush[self.sq_track] = list(step["notes"])
        self.sq_save(song)

    def sq_change(self, field, amount):
        song = self.sq_song()
        step = self.sq_track_of(song)["steps"][self.sq_step] if self.sq_step is not None else None
        if not step:
            return
        if field == "vel":
            step["vel"] = max(1, min(127, step["vel"] + amount))
        else:
            step["len"] = max(0.5, min(16.0, step["len"] + amount))
        self.sq_save(song)

    def sq_length(self, step):
        import sequencer
        song = self.sq_song()
        track = self.sq_track_of(song)
        track["len"] = max(1, min(sequencer.NSTEP, track["len"] + step))
        if self.sq_step is not None and self.sq_step >= track["len"]:
            self.sq_step = None
        self.sq_save(song)

    def sq_clear(self):
        song = self.sq_song()
        track = self.sq_track_of(song)
        track["steps"] = [None] * len(track["steps"])
        self.sq_step = None
        self.sq_save(song)
        self.app.say(f"Track {self.sq_track + 1} cleared in {self.sq_pattern(song)}", 2)

    def sq_octave(self, step):
        self.sq_oct[self.sq_track] = max(0, min(8, self.sq_oct[self.sq_track] + step))
        self.sq_rev += 1

    def sq_root(self):
        song = self.sq_song()
        song["root"] = (song["root"] + 1) % 12
        self.sq_save(song)

    def sq_scale(self):
        import sequencer
        song = self.sq_song()
        names = list(sequencer.SCALES)
        song["scale"] = names[(names.index(song["scale"]) + 1) % len(names)]
        self.sq_save(song)
