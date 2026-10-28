"""The Studio's XO-4 tab: XO-4's patterns by touch (xo4.py plays them). Mixed into deskui.DeskUI; full screen, as
the decks are: the step grid and the keys need the height the tab bar takes.

  header      < HOME, the patterns A-H (tap: edit it and play it from the next bar; the one playing underlined, one
              waiting outlined), the tempo, PLAY / STOP (the box's transport, as the pads' SEQ)
  tracks      DRUMS, SYN 1, SYN 2, MIDI; the track's length (LEN - / +, 1-64); HOLD CLR empties the track here
  steps       16 a page, the playhead lit. DRUMS: a tap puts the pad picked below on the step or takes it off.
              The rest: a tap on an empty step places the last notes there and selects it; a tap on the selected
              step empties it; on another, selects it
  step row    the pages (1-4, as many as the length needs); the selected step's VEL and LEN (in steps) - / +
  below       DRUMS: the 16 pads (pick one; stopped, it sounds). The rest: OCT - / +, KEY and SCALE (the note keys
              offer the scale's notes), and 14 note keys from the octave: a tap adds the note to the selected step
              or takes it off (four at most: a chord); stopped, it sounds. SYN 1 and SYN 2: SOUND opens the synth's
              page (below)

The SOUND page (a synth track's): < XO-4 back, HEAR (its last notes), six starting sounds (KEYS, BASS, BELL,
PLUCK, PAD, LEAD), and the patch's settings, each - / + (held: four steps): RATIO, BRIGHT (the modulation
index), BR DECAY and BR HOLD (how the brightness falls, and what stays), ATTACK, DECAY, SUSTAIN, RELEASE, LEVEL.
While stopped, a change sounds the track's last notes.
"""

import sloopstyle as st

W, H, HDR_H = 480, 320, 34
TRACK_LABELS = ("DRUMS", "SYN 1", "SYN 2", "MIDI")
OCTAVES = (4, 4, 2, 3)                          # the note keys' octave a track starts on (SYN 2: a bass)
KEYS = 14                                       # note keys: two rows of seven
RED = (255, 112, 92)


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
        return (self.xo4_rev, self.xo4_track, self.xo4_edit, self.xo4_step, self.xo4_page, self.xo4_pad,
                tuple(self.xo4_oct), a.seq_playing(), x and x.step, x and x.pattern, x and x.queued, a.clock_text(),
                self.xo4_sound)

    # ---- drawing

    def draw_xo4(self, img, d, now):
        import xo4
        a, t = self.app, self.theme
        song = self.xo4_song()
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
        st.text(img, (346, 9), (a.clock_text() or "")[:8], t.c[3])
        self.button(img, d, (W - 64, 3, W - 4, HDR_H - 5), "STOP" if playing else "PLAY", a.seq_play, on=playing,
                    key="xo4-play")
        d.line((0, HDR_H - 1, W, HDR_H - 1), fill=t.c[0], width=2)
        y = HDR_H + 4                           # the tracks, the length, clear
        for k, label in enumerate(TRACK_LABELS):
            self.button(img, d, (4 + k * 64, y, 64 + k * 64, y + 32), label, lambda k=k: self.xo4_pick_track(k),
                        color=t.track[k], on=k == self.xo4_track, key=("xo4-track", k))
        self.button(img, d, (264, y, 296, y + 32), "-", lambda: self.xo4_length(-1), key="xo4-len-")
        self.centre(img, (296, y, 356, y + 32), f"LEN {track['len']}", t.hi)
        self.button(img, d, (356, y, 388, y + 32), "+", lambda: self.xo4_length(1), key="xo4-len+")
        self.widget((394, y, W - 4, y + 32), "hold", self.xo4_clear, "xo4-clear")
        d.rectangle((394, y, W - 4, y + 32), fill=t.hi if self.lit("xo4-clear") else t.grey[0])
        self.centre(img, (394, y, W - 4, y + 32), "HOLD CLR", t.bg if self.lit("xo4-clear") else RED)
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
            if self.xo4_track == 0:
                mine = bool(step and self.xo4_pad in step["notes"])
            else:
                mine = bool(step)
            fill = t.hi if idx == here else colour if mine else t.grey[1] if k % 4 == 0 else t.grey[0]
            d.rectangle(box, fill=fill)
            if idx == self.xo4_step and self.xo4_track:
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
            st.text(img, (164, y + 9), f"STEPS PUT PAD {self.xo4_pad + 1} ON OR OFF", t.c[2])

    def draw_xo4_pads(self, img, d):
        t, kit = self.theme, self.app.kit()
        top, pw = HDR_H + 136, W // 8
        for i in range(16):
            r = 1 - i // 8                      # pads 1-8 the bottom row, as on the PADS grid
            box = (i % 8 * pw + 2, top + r * 74, (i % 8 + 1) * pw - 3, top + r * 74 + 68)
            colour = t.track[(3 - i // 4) % 4]
            on = i == self.xo4_pad
            d.rectangle(box, fill=colour if on else t.grey[0], outline=colour, width=2)
            st.text(img, (box[0] + 5, box[1] + 4), str(i + 1), t.bg if on else colour)
            sample = kit["pads"][i]["sample"]
            if sample:
                from pathlib import Path
                st.text(img, (box[0] + 5, box[3] - 20), Path(sample).stem.replace("808-", "").replace("-", "")[:6],
                        t.bg if on else t.c[3])
            self.widget(box, "tap", lambda i=i: self.xo4_pick_pad(i), ("xo4-pad", i))

    def draw_xo4_keys(self, img, d, song, track):
        import xo4
        t = self.theme
        y = HDR_H + 136
        octave = self.xo4_oct[self.xo4_track]
        self.button(img, d, (4, y, 36, y + 30), "-", lambda: self.xo4_octave(-1), key="xo4-oct-")
        self.centre(img, (36, y, 100, y + 30), f"OCT {octave}", t.hi)
        self.button(img, d, (100, y, 132, y + 30), "+", lambda: self.xo4_octave(1), key="xo4-oct+")
        self.button(img, d, (140, y, 240, y + 30), "KEY " + xo4.NOTE_NAMES[song["root"]], self.xo4_root,
                    key="xo4-root")
        self.button(img, d, (246, y, 380, y + 30), song["scale"], self.xo4_scale, key="xo4-scale")
        if self.xo4_track == xo4.MIDI:
            st.text(img, (388, y + 8), f"CH {song['midi_channel'] + 1}", t.c[3])
        else:                                   # a synth: its SOUND page
            self.button(img, d, (386, y, W - 4, y + 30), "SOUND", self.xo4_sound_open, color=t.track[self.xo4_track],
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
        x = getattr(self.app, "xo4", None)
        if x:
            x.send("pick", p)
        if not self.app.seq_playing():
            song = self.xo4_song()
            song["pattern"] = p
            self.xo4_save(song)

    def xo4_pick_track(self, k):
        self.xo4_track, self.xo4_step, self.xo4_page, self.xo4_sound = k, None, 0, False
        self.xo4_rev += 1

    def xo4_pick_pad(self, i):
        self.xo4_pad = i
        self.xo4_rev += 1
        if self.app.pads and not self.app.seq_playing():
            self.app.pads.send("tap", i, 100)   # (stopped: heard as it's picked)

    def xo4_go_page(self, pg):
        self.xo4_page = pg
        self.xo4_rev += 1

    def xo4_track_of(self, song):
        return song["patterns"][self.xo4_pattern(song)][self.xo4_track]

    def xo4_tap(self, idx):
        song = self.xo4_song()
        track = self.xo4_track_of(song)
        step = track["steps"][idx]
        if self.xo4_track == 0:                 # DRUMS: the pad picked, on or off
            notes = list(step["notes"]) if step else []
            notes = [n for n in notes if n != self.xo4_pad] if self.xo4_pad in notes else notes + [self.xo4_pad]
            track["steps"][idx] = {"notes": notes, "vel": step["vel"] if step else 100, "len": 1.0} if notes else None
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
